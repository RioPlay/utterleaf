"""Fail closed on package identity, debug builds, downgrades and signer changes."""
import json
import re
import sys
import urllib.request
from pathlib import Path


def package_metadata(badging, version, certificate):
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.M)
    if not package or package[1] != "org.utterleaf.voice" or package[3] != version:
        raise ValueError("APK package/version does not match the Android release")
    if re.search(r"^application-debuggable", badging, re.M):
        raise ValueError("Public updates cannot use a debuggable APK")
    if not re.fullmatch(r"[a-f0-9]{64}", certificate):
        raise ValueError("Invalid signing certificate fingerprint")
    return {"packageName": package[1], "versionCode": int(package[2]),
            "versionName": package[3], "signingCertificateSha256": certificate}


def verify_upgrade(current, previous):
    if current["packageName"] != previous["packageName"]:
        raise ValueError("Update package identity changed")
    if current["versionCode"] <= previous["versionCode"]:
        raise ValueError("Every published update must increase versionCode")
    if current["signingCertificateSha256"] != previous["signingCertificateSha256"]:
        raise ValueError("Signing identity changed without an approved key-rotation plan")


def main():
    badging, version, certificate_file, releases_file, output = sys.argv[1:]
    current = package_metadata(Path(badging).read_text(), version, Path(certificate_file).read_text().strip())
    for release in json.loads(Path(releases_file).read_text()):
        if release["draft"] or not (release.get("name") or "").startswith("Utterleaf Android "):
            continue
        asset = next((a for a in release["assets"] if a["name"] == "version.json"), None)
        if asset is None:
            raise ValueError("Earlier signed release is missing upgrade metadata")
        url = asset["browser_download_url"]
        if not url.startswith("https://github.com/RioPlay/utterleaf/releases/download/android-v"):
            raise ValueError("Unexpected release metadata source")
        with urllib.request.urlopen(url, timeout=30) as response:
            previous = json.loads(response.read(16384))
        verify_upgrade(current, previous)
    Path(output).write_text(json.dumps(current, indent=2) + "\n")


if __name__ == "__main__":
    main()
