"""Match resolved Maven versions locally against OSV public advisories.

No project information is uploaded. This covers Maven and the Gradle distribution,
not native sources, JDK/SDK binaries, or undisclosed vulnerabilities. OSV enumerations and ranges are evaluated as a union using Apache Maven
ComparableVersion; unsupported range types/events fail explicitly.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

DATABASE_URL = "https://osv-vulnerabilities.storage.googleapis.com/Maven/all.zip"
KAPT_ADVISORY = "GHSA-r937-wjx7-w2jp"
MAVEN_VERSION = "3.9.11"
MAVEN_JAR = f"maven-artifact-{MAVEN_VERSION}.jar"
MAVEN_URL = f"https://repo1.maven.org/maven2/org/apache/maven/maven-artifact/{MAVEN_VERSION}/{MAVEN_JAR}"
MAVEN_SHA256 = "0bfd1c121f907642344311d81e4dfd93eba6c24dc712cc0aeae273eb22833022"


@contextmanager
def maven_comparator(jar):
    if hashlib.sha256(jar.read_bytes()).hexdigest() != MAVEN_SHA256:
        raise ValueError("Maven comparator JAR checksum mismatch")
    java_home = os.environ.get("JAVA_HOME")
    java = str(Path(java_home) / "bin" / "java") if java_home else shutil.which("java")
    if not java:
        raise ValueError("JDK 17 is required for Maven version comparison")
    helper = Path(__file__).with_name("MavenVersionCompare.java")
    process = subprocess.Popen([java, "--class-path", str(jar.resolve()), str(helper)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    def compare(left, right):
        if any(not value or any(char in value for char in "\t\r\n") for value in (left, right)):
            raise ValueError("Invalid Maven version comparison input")
        process.stdin.write(left + "\t" + right + "\n")
        process.stdin.flush()
        result = process.stdout.readline().strip()
        if result not in ("-1", "0", "1"):
            raise ValueError(f"Maven version comparator failed: {result or process.stderr.read()}")
        return int(result)
    try:
        yield compare
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


def affected_version(version, affected, compare):
    matched = version in affected.get("versions", [])
    ranges = affected.get("ranges", [])
    if not ranges and not affected.get("versions"):
        raise ValueError("Neither enumerated versions nor ranges present")
    for interval in ranges:
        if interval["type"] != "ECOSYSTEM":
            raise ValueError(f"Unsupported Maven range: {interval['type']}")
        active = False
        for event in interval["events"]:
            if "introduced" in event:
                active = event["introduced"] == "0" or compare(version, event["introduced"]) >= 0
            elif "fixed" in event:
                if active and compare(version, event["fixed"]) < 0:
                    matched = True
                active = False
            elif "last_affected" in event:
                if active and compare(version, event["last_affected"]) <= 0:
                    matched = True
                active = False
            elif "limit" in event:
                if active and compare(version, event["limit"]) < 0:
                    matched = True
                active = False
            else:
                raise ValueError(f"Unsupported range event: {event}")
        if active:
            matched = True
    return matched


def scan(inventory, database, compare):
    rows = inventory["dependencies"]
    if not rows or not inventory["configurations"]:
        raise ValueError("Empty inventory; resolve dependencies successfully first")
    coordinates = {(row["name"], row["version"]) for row in rows}
    coordinates.add(("org.gradle:gradle-core", inventory["gradleVersion"]))
    coordinates.add(("org.apache.maven:maven-artifact", MAVEN_VERSION))
    kapt_used = any("kapt" in name.lower() for name in inventory["configurations"])
    findings = []
    with zipfile.ZipFile(database) as archive:
        if not archive.namelist():
            raise ValueError("Empty advisory database")
        for filename in archive.namelist():
            advisory = json.loads(archive.read(filename))
            if advisory.get("withdrawn"):
                continue
            for affected in advisory.get("affected", []):
                package = affected.get("package", {})
                if package.get("ecosystem") != "Maven":
                    continue
                name = package["name"]
                relevant = {version for coordinate, version in coordinates if coordinate == name}
                for version in sorted(relevant):
                    if not affected_version(version, affected, compare):
                        continue
                    not_applicable = (advisory["id"] == KAPT_ADVISORY
                                      and name == "org.jetbrains.kotlin:kotlin-gradle-plugin" and not kapt_used)
                    findings.append({
                        "id": advisory["id"], "package": name, "version": version,
                        "summary": advisory.get("summary", ""),
                        "status": "not-applicable" if not_applicable else "affected",
                        "reason": "Upstream fix concerns KAPT incremental cache; no KAPT configuration is present"
                            if not_applicable else "OSV matches this resolved version as affected",
                    })
    return {"coordinate_count": len(coordinates),
            "configuration_count": len(inventory["configurations"]), "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("build/reports/security/dependencies.json"))
    parser.add_argument("--database", type=Path, default=Path("build/reports/security/maven-advisories.zip"))
    parser.add_argument("--download", action="store_true", help="Download public advisories; uploads nothing")
    parser.add_argument("--output", type=Path, default=Path("build/reports/security/audit.json"))
    parser.add_argument("--maven-jar", type=Path, default=Path("build/reports/security") / MAVEN_JAR)
    args = parser.parse_args()
    try:
        if args.download:
            args.database.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(DATABASE_URL, timeout=60) as response:
                payload = response.read()
            # Validate before replacing a previous local snapshot.
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Corrupt advisory archive")
            args.database.write_bytes(payload)
            with urllib.request.urlopen(MAVEN_URL, timeout=60) as response:
                comparator = response.read()
            if hashlib.sha256(comparator).hexdigest() != MAVEN_SHA256:
                raise ValueError("Downloaded Maven comparator JAR checksum mismatch")
            args.maven_jar.parent.mkdir(parents=True, exist_ok=True)
            args.maven_jar.write_bytes(comparator)
        with maven_comparator(args.maven_jar) as compare:
            result = scan(json.loads(args.inventory.read_text()), args.database, compare)
        result["database_sha256"] = hashlib.sha256(args.database.read_bytes()).hexdigest()
        result["database_source"] = DATABASE_URL
        result["maven_comparator"] = {"version": MAVEN_VERSION, "sha256": MAVEN_SHA256}
        result["status"] = "complete"
        result["scanned_at_utc"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        for finding in result["findings"]:
            print(f"{finding['status']}: {finding['package']}:{finding['version']} {finding['id']}")
        affected = sum(item["status"] == "affected" for item in result["findings"])
        print(f"{result['coordinate_count']} coordinates, {result['configuration_count']} configurations; {affected} affected advisory matches")
        return 1 if affected else 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        # Never leave a previous successful report looking current after a failure.
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"status": "incomplete", "error": str(error)}) + "\n")
        except OSError:
            pass
        print(f"Audit incomplete: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
