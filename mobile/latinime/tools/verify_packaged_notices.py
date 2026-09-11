"""Compare APK notice bytes and generated hashes with current reviewed source inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def _fields(data: bytes):
    """Read wire fields from the pinned AGP dependency report; fail on malformed data."""
    position = 0

    def varint():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(data):
                raise ValueError("Truncated dependency report")
            byte = data[position]
            position += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Invalid dependency report varint")

    while position < len(data):
        key = varint()
        field, wire = key >> 3, key & 7
        if field == 0:
            raise ValueError("Invalid dependency report field")
        if wire == 0:
            varint()
            continue
        length = varint() if wire == 2 else {1: 8, 5: 4}.get(wire)
        if length is None or length > len(data) - position:
            raise ValueError("Unsupported or truncated dependency report field")
        value = data[position:position + length]
        position += length
        if wire == 2:
            yield field, value


def resolved_coordinates(report: Path) -> set[str]:
    # Observed pinned AGP schema: report.library(1).coordinate(1): group1/artifact2/version5.
    # Compare semantic identities, not protobuf ordering or platform-specific artifact bytes.
    coordinates = set()
    for field, library in _fields(report.read_bytes()):
        if field != 1:
            continue
        coordinate = [value for key, value in _fields(library) if key == 1]
        if len(coordinate) != 1:
            raise ValueError("Unexpected dependency report coordinate schema")
        values = dict(_fields(coordinate[0]))
        coordinates.add(":".join(values[key].decode("utf-8") for key in (1, 2, 5)))
    if not coordinates:
        raise ValueError("Empty dependency report")
    return coordinates


def verify(apk: Path) -> dict:
    foundation = Path(__file__).resolve().parents[1]
    repo = foundation.parents[1]
    expected = json.loads((foundation / "notices/catalog.json").read_text(encoding="utf-8"))
    inventory = json.loads((foundation / "notices/runtime-dependencies.json").read_text(encoding="utf-8"))
    report = (repo / inventory["source"]).resolve()
    if not report.is_relative_to(foundation / "app/build"):
        raise ValueError("Dependency report outside foundation build")
    if resolved_coordinates(report) != {entry["coordinate"] for entry in inventory["dependencies"]}:
        raise ValueError("Resolved dependencies changed; update the reviewed notice inventory")
    with zipfile.ZipFile(apk) as archive:
        packaged = json.loads(archive.read("assets/notices/catalog.json"))
        names = [name for name in archive.namelist() if name.startswith("assets/notices/")]
        required = {"assets/notices/catalog.json"}
        for document in expected["documents"]:
            source = (repo / document["source_path"]).resolve()
            if not source.is_relative_to(foundation):
                raise ValueError("Notice source outside foundation")
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if "refresh_from_source" not in document and digest != document["sha256"]:
                raise ValueError(f"Unreviewed source hash: {document['file']}")
            name = "assets/notices/" + document["file"]
            required.add(name)
            if archive.read(name) != data:
                raise ValueError(f"Packaged notice differs from current source: {document['file']}")
            document["sha256"] = digest
        if len(names) != len(required) or set(names) != required:
            raise ValueError("Duplicate, missing or unexpected packaged notice entries")
        if packaged != expected:
            raise ValueError("Packaged catalog differs from refreshed source catalog")
    return {"apk": str(apk), "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            "verified_documents": len(expected["documents"]),
            "scope": "Exact current-source notice bytes and catalog; not full licensing compliance"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path, nargs="+")
    arguments = parser.parse_args()
    for candidate in arguments.apk:
        print(json.dumps(verify(candidate), sort_keys=True))
