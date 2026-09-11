// Copyright 2026 Utterleaf contributors. SPDX-License-Identifier: Apache-2.0
#include "dictionary_storage.h"

#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <vector>
#include "dictionary/structure/dictionary_structure_with_buffer_policy_factory.h"
#ifdef UTTERLEAF_STORAGE_TESTING
#include <jni.h>
#include "suggest/core/dictionary/dictionary.h"
#endif

namespace latinime {
#ifdef UTTERLEAF_STORAGE_TESTING
thread_local bool gStorageFailNextNativeOpen = false;
#endif
namespace {
constexpr const char *MARKER = ".utterleaf-storage-v1";
constexpr const char *MAGIC = "Utterleaf dictionary transaction v1\n";
bool sameDirectory(int first, int second) {
    struct stat a{}, b{};
    return first >= 0 && second >= 0 && fstat(first, &a) == 0 && fstat(second, &b) == 0
            && a.st_dev == b.st_dev && a.st_ino == b.st_ino;
}
int parentFor(const char *path, std::string *name) {
    if (!path || path[0] != '/' || strlen(path) >= PATH_MAX) return -1;
    const std::string value(path);
    const size_t slash = value.rfind('/');
    *name = value.substr(slash + 1);
    if (name->empty() || *name == "." || *name == ".." || name->size() > NAME_MAX) return -1;
    return open((slash == 0 ? "/" : value.substr(0, slash)).c_str(),
            O_RDONLY | O_DIRECTORY | O_CLOEXEC);
}
std::string anchored(int directory, const std::string &name) {
    return "/proc/self/fd/" + std::to_string(directory) + "/" + name;
}
bool entries(int directory, std::vector<std::string> *names) {
    // An independent directory description keeps readdir offsets out of the held lock fd.
    const int copy = openat(directory, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (copy < 0) return false;
    DIR *stream = fdopendir(copy);
    if (!stream) { close(copy); return false; }
    errno = 0;
    while (dirent *entry = readdir(stream)) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) {
            names->emplace_back(entry->d_name);
            if (names->size() > 16) { closedir(stream); return false; }
        }
    }
    const bool okay = errno == 0;
    closedir(stream);
    return okay;
}
bool dictionaryFiles(int directory, const std::string &basename,
        std::vector<std::string> *names) {
    if (!entries(directory, names)) return false;
    static const char *suffixes[] = {".header", ".body", ".trie", ".freq", ".tat",
            ".bigram_freq", ".bigram_lookup", ".bigram_index_freq", ".shortcut_shortcut",
            ".shortcut_lookup", ".shortcut_index_shortcut"};
    for (const std::string &name : *names) {
        bool expected = false;
        for (const char *suffix : suffixes) if (name == basename + suffix) expected = true;
        struct stat info{};
        if (!expected || fstatat(directory, name.c_str(), &info, AT_SYMLINK_NOFOLLOW) != 0
                || !S_ISREG(info.st_mode) || info.st_nlink != 1) return false;
    }
    return true;
}
bool recognizedMarker(int stage) {
    const int marker = openat(stage, MARKER, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (marker < 0) return false;
    struct stat info{};
    if (fstat(marker, &info) != 0 || !S_ISREG(info.st_mode) || info.st_nlink != 1
            || info.st_size != static_cast<off_t>(strlen(MAGIC))) { close(marker); return false; }
    char content[64]{};
    const ssize_t count = read(marker, content, sizeof(content));
    close(marker);
    return count == static_cast<ssize_t>(strlen(MAGIC))
            && memcmp(content, MAGIC, static_cast<size_t>(count)) == 0;
}
} // namespace

StorageGeneration::~StorageGeneration() { if (fd >= 0) close(fd); }
bool StorageFault::stop(int checkpoint) {
#ifdef UTTERLEAF_STORAGE_TESTING
    if (stage.load() != checkpoint) return false;
    reached.store(checkpoint);
    if (mode.load() == 2) while (!released.load()) usleep(1000);
    return mode.load() == 1;
#else
    (void)checkpoint;
    return false;
#endif
}
thread_local StorageTransaction *StorageTransaction::sCurrent = nullptr;

StorageReadLock::StorageReadLock(const char *path) {
    std::string name;
    mParent = parentFor(path, &name);
    if (mParent < 0) return;
    if (!StorageTransaction::borrowsReadLock(mParent, name)
            && flock(mParent, LOCK_SH | LOCK_NB) != 0) return;
    struct stat info{};
    if (fstatat(mParent, name.c_str(), &info, AT_SYMLINK_NOFOLLOW) != 0
            || (!S_ISDIR(info.st_mode) && !S_ISREG(info.st_mode))) return;
    if (S_ISDIR(info.st_mode)) {
        mDirectory = openat(mParent, name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (mDirectory < 0) return;
    }
    mValid = true;
}
StorageReadLock::~StorageReadLock() {
    if (mDirectory >= 0) close(mDirectory);
    if (mParent >= 0) close(mParent);
}
std::shared_ptr<StorageGeneration> StorageReadLock::generation() const {
    if (!mValid || mDirectory < 0) return nullptr;
    const int copy = fcntl(mDirectory, F_DUPFD_CLOEXEC, 0);
    return copy < 0 ? nullptr : std::make_shared<StorageGeneration>(copy);
}

StorageTransaction::StorageTransaction(const char *path,
        std::shared_ptr<StorageGeneration> *generation, StorageFault *fault)
        : mGeneration(generation), mFault(fault), mPrevious(sCurrent) {
    // No unrelated nested transaction may borrow a currently held writer lock.
    if (sCurrent || !generation) return;
    mParent = parentFor(path, &mName);
    mStageName = mName + ".utterleaf-stage";
    if (mParent < 0 || mStageName.size() > NAME_MAX
            || flock(mParent, LOCK_EX | LOCK_NB) != 0) return;
    struct stat info{};
    const int status = fstatat(mParent, mName.c_str(), &info, AT_SYMLINK_NOFOLLOW);
    if (status != 0 && errno != ENOENT) return;
    if (*generation) {
        const int original = openat(mParent, mName.c_str(),
                O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        const bool same = sameDirectory(original, (*generation)->fd);
        std::vector<std::string> names;
        const bool recognized = same && dictionaryFiles(original, mName, &names);
        if (original >= 0) close(original);
        if (!recognized) return;
    } else if (status == 0) {
        return; // A new in-memory dictionary cannot overwrite an existing generation.
    }
    sCurrent = this;
    mAdmitted = true;
}
StorageTransaction::~StorageTransaction() {
    if (sCurrent == this) sCurrent = mPrevious;
    if (mCandidate >= 0) close(mCandidate);
    if (mStage >= 0) close(mStage);
    if (mParent >= 0) close(mParent);
}
bool StorageTransaction::borrowsReadLock(int parent, const std::string &basename) {
    return sCurrent && sCurrent->mAdmitted && basename == sCurrent->mName
            && (sameDirectory(parent, sCurrent->mParent) || sameDirectory(parent, sCurrent->mStage));
}
StorageTransaction *StorageTransaction::current(const char *path) {
    if (!sCurrent) return nullptr;
    std::string name;
    const int parent = parentFor(path, &name);
    const bool matches = parent >= 0 && name == sCurrent->mName
            && sameDirectory(parent, sCurrent->mParent);
    if (parent >= 0) close(parent);
    return matches ? sCurrent : nullptr;
}
bool StorageTransaction::stop(int checkpoint) { return mFault && mFault->stop(checkpoint); }
bool StorageTransaction::validateCurrent() {
    const auto policy = DictionaryStructureWithBufferPolicyFactory::newPolicyForExistingDictFile(
            anchored(mParent, mName).c_str(), 0, 0, false);
    return policy != nullptr;
}
bool StorageTransaction::syncParents() {
    return fsync(mParent) == 0 && (mStage < 0 || fsync(mStage) == 0);
}
bool StorageTransaction::cleanStage() {
    if (mStage < 0 || !recognizedMarker(mStage)) return false;
    std::vector<std::string> children;
    if (!entries(mStage, &children)) return false;
    for (const std::string &child : children) if (child != MARKER && child != mName) return false;
    const int candidate = openat(mStage, mName.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (candidate < 0 && errno != ENOENT) return false;
    if (candidate >= 0) {
        std::vector<std::string> names;
        if (!dictionaryFiles(candidate, mName, &names)) { close(candidate); return false; }
        for (const auto &name : names) if (unlinkat(candidate, name.c_str(), 0) != 0) {
            close(candidate); return false;
        }
        close(candidate);
        if (unlinkat(mStage, mName.c_str(), AT_REMOVEDIR) != 0) return false;
    }
    if (unlinkat(mStage, MARKER, 0) != 0) return false;
    close(mStage); mStage = -1;
    return unlinkat(mParent, mStageName.c_str(), AT_REMOVEDIR) == 0 && fsync(mParent) == 0;
}
bool StorageTransaction::prepare(std::string *basePath) {
    if (!mAdmitted || stop(1)) return false;
    mStage = openat(mParent, mStageName.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (mStage >= 0) {
        // A staged generation might be the previous original after an interrupted exchange.
        // Never delete it unless the current original passes existing structural checks and sync.
        if (!validateCurrent() || !syncParents() || !cleanStage()) return false;
    } else if (errno != ENOENT) return false;
    if (mkdirat(mParent, mStageName.c_str(), S_IRWXU) != 0) return false;
    mStage = openat(mParent, mStageName.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (mStage < 0) return false;
    const int marker = openat(mStage, MARKER, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (marker < 0) return false;
    const bool markerOkay = write(marker, MAGIC, strlen(MAGIC)) == static_cast<ssize_t>(strlen(MAGIC))
            && fsync(marker) == 0;
    const int markerClose = close(marker);
    if (!markerOkay || markerClose != 0 || mkdirat(mStage, mName.c_str(), 0700) != 0) return false;
    mCandidate = openat(mStage, mName.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (mCandidate < 0) return false;
    *basePath = anchored(mCandidate, mName);
    return true;
}
bool StorageTransaction::finishFile(FILE *file) {
    if (!file) return false;
    bool okay = fflush(file) == 0;
    if (okay) okay = fsync(fileno(file)) == 0;
    if (sCurrent && sCurrent->stop(2)) okay = false;
    const bool closed = fclose(file) == 0;
    return okay && closed;
}
bool StorageTransaction::publish() {
    if (!mAdmitted || mCandidate < 0 || stop(3) || fsync(mCandidate) != 0
            || fsync(mStage) != 0) return false;
    const auto candidate = DictionaryStructureWithBufferPolicyFactory::newPolicyForExistingDictFile(
            anchored(mStage, mName).c_str(), 0, 0, false);
    if (!candidate || stop(4)) return false;
    // Linux atomic exchange has no destructive fallback on unsupported filesystems/kernels.
    const unsigned flags = *mGeneration ? 2u /* RENAME_EXCHANGE */ : 1u /* RENAME_NOREPLACE */;
    if (syscall(__NR_renameat2, mStage, mName.c_str(), mParent, mName.c_str(), flags) != 0) return false;
    mPublished = true;
    if (stop(5) || !syncParents() || stop(6)) return false;
    const int current = openat(mParent, mName.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (current < 0 || !validateCurrent()) { if (current >= 0) close(current); return false; }
    *mGeneration = std::make_shared<StorageGeneration>(current);
    close(mCandidate); mCandidate = -1;
    // Failure to remove a backup is reported; it is retained safely for a later validated cleanup.
    return cleanStage();
}
} // namespace latinime

#ifdef UTTERLEAF_STORAGE_TESTING
extern "C" JNIEXPORT void JNICALL Java_org_utterleaf_keyboard_StorageFaults_configureNative(
        JNIEnv *, jobject, jlong owner, jint stage, jint mode) {
    if (!owner) return;
    auto &fault = reinterpret_cast<latinime::Dictionary *>(owner)->storageFaultForTesting();
    fault.released.store(false);
    fault.reached.store(0);
    fault.mode.store(mode);
    fault.stage.store(stage);
}
extern "C" JNIEXPORT jint JNICALL Java_org_utterleaf_keyboard_StorageFaults_reachedNative(
        JNIEnv *, jobject, jlong owner) {
    return owner ? reinterpret_cast<latinime::Dictionary *>(owner)->storageFaultForTesting().reached.load() : 0;
}
extern "C" JNIEXPORT void JNICALL Java_org_utterleaf_keyboard_StorageFaults_releaseNative(
        JNIEnv *, jobject, jlong owner) {
    if (owner) reinterpret_cast<latinime::Dictionary *>(owner)->storageFaultForTesting().released.store(true);
}
#endif
