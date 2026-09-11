// Copyright 2026 Utterleaf contributors. SPDX-License-Identifier: Apache-2.0
#ifndef UTTERLEAF_DICTIONARY_STORAGE_H
#define UTTERLEAF_DICTIONARY_STORAGE_H

#include <atomic>
#include <cstdio>
#include <memory>
#include <string>

namespace latinime {
#ifdef UTTERLEAF_STORAGE_TESTING
extern thread_local bool gStorageFailNextNativeOpen;
#endif
// Keeping the directory descriptor alive prevents inode reuse from accepting a stale writer.
struct StorageGeneration {
    explicit StorageGeneration(int descriptor) : fd(descriptor) {}
    ~StorageGeneration();
    const int fd;
};

struct StorageFault {
#ifdef UTTERLEAF_STORAGE_TESTING
    std::atomic<int> stage{0}, mode{0}, reached{0};
    std::atomic<bool> released{false};
#endif
    bool stop(int checkpoint);
};

class StorageReadLock {
 public:
    explicit StorageReadLock(const char *path);
    ~StorageReadLock();
    bool valid() const { return mValid; }
    std::shared_ptr<StorageGeneration> generation() const;
 private:
    int mParent = -1, mDirectory = -1;
    bool mValid = false;
};

class StorageTransaction {
 public:
    StorageTransaction(const char *path, std::shared_ptr<StorageGeneration> *generation,
            StorageFault *fault = nullptr);
    ~StorageTransaction();
    bool admitted() const { return mAdmitted; }
    bool published() const { return mPublished; }
    bool prepare(std::string *basePath);
    bool publish();
    bool stop(int checkpoint);
    static StorageTransaction *current(const char *path);
    static bool borrowsReadLock(int parent, const std::string &basename);
    static bool finishFile(FILE *file);
 private:
    bool cleanStage();
    bool validateCurrent();
    bool syncParents();
    std::string mName, mStageName;
    int mParent = -1, mStage = -1, mCandidate = -1;
    std::shared_ptr<StorageGeneration> *mGeneration;
    StorageFault *mFault;
    bool mAdmitted = false, mPublished = false;
    StorageTransaction *mPrevious;
    static thread_local StorageTransaction *sCurrent;
};
} // namespace latinime
#endif
