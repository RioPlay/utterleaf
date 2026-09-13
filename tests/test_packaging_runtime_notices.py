"""A short license label must never stand in for distributable runtime notices."""
import email
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "packaging" / "collect_notices.py"
    spec = importlib.util.spec_from_file_location("runtime_notices_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "SITE", tmp_path / "site")
    monkeypatch.setattr(module, "DIST", tmp_path / "bundle")
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32", version_info=(3, 14, 6)))
    files = []
    for name, content in [("LICENSE", "Complete primary terms"),
                          ("dependency/LICENSE", "Complete dependency terms")]:
        relative = "runtime/example/" + name
        path = tmp_path / "packaging" / "notices" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files.append({"path": relative, "destination": name,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "source": "https://example.invalid/exact-revision/" + name})
    payload = module.DIST / "_internal" / "example.dll"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"reviewed binary fixture")
    entry = {"name": "Example", "version": "1.0", "license": "MIT",
             "review_status": "complete", "files": files,
             "payloads": {"example.dll": hashlib.sha256(payload.read_bytes()).hexdigest()}}
    manifest = {"python_version": "3.14.6", "windows_review_status": "complete",
                "packages": {"example": entry}, "windows_runtime": {"example": entry}}
    monkeypatch.setattr(module, "runtime_notice_manifest", lambda: manifest)
    return module, manifest, entry, tmp_path / "output"


def package_metadata(version="1.0", name="example"):
    return email.message_from_string(f"Name: {name}\nVersion: {version}\nLicense: MIT\n")


def test_expression_only_or_unreviewed_version_cannot_ship(runtime):
    module, _, _, output = runtime
    for meta in [package_metadata(name="unknown"), package_metadata(version="2.0")]:
        with pytest.raises(SystemExit, match="full license text unavailable"):
            module.copy_license_files(module.SITE / "example.dist-info", meta, output)
    assert not output.exists()


def test_exact_fallback_retains_distinct_component_texts_and_provenance(runtime):
    module, _, entry, output = runtime
    module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output)
    assert (output / "LICENSE").read_text() == "Complete primary terms"
    assert (output / "dependency" / "LICENSE").read_text() == "Complete dependency terms"
    assert json.loads((output / "PROVENANCE.json").read_text()) == entry
    assert not (output / "LICENSE-DECLARED.txt").exists()


def test_wheel_full_text_does_not_need_a_fallback_record(runtime):
    module, _, _, output = runtime
    info = module.SITE / "unknown.dist-info"
    (info / "licenses").mkdir(parents=True)
    (info / "licenses" / "LICENSE").write_text("Full wheel terms")
    module.copy_license_files(info, package_metadata(name="unknown"), output)
    assert (output / "LICENSE").read_text() == "Full wheel terms"


def test_reviewed_package_level_notice_is_copied_and_verified(runtime):
    module, _, entry, output = runtime
    item = entry["files"][0]
    item["source_root"] = "site"
    item["path"] = "example/ThirdPartyNotices.txt"
    source = module.SITE / item["path"]
    source.parent.mkdir(parents=True)
    source.write_text("Complete primary terms")
    module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output)
    assert (output / "LICENSE").read_text() == "Complete primary terms"
    source.write_text("Unreviewed replacement")
    with pytest.raises(SystemExit, match="missing or changed reviewed notice"):
        module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output)


@pytest.mark.parametrize("missing", [False, True])
def test_changed_or_missing_reviewed_text_prevents_distribution(runtime, missing):
    module, _, entry, output = runtime
    path = module.ROOT / "packaging" / "notices" / entry["files"][0]["path"]
    if missing:
        path.rename(path.with_suffix(".unavailable"))
    else:
        path.write_text("Short replacement label")
    with pytest.raises(SystemExit, match="missing or changed reviewed notice"):
        module.copy_reviewed_notice_files(entry, output)
    assert not output.exists()


def test_unfinished_component_review_prevents_distribution(runtime):
    module, _, entry, output = runtime
    entry["review_status"] = "pending"
    with pytest.raises(SystemExit, match="component notice review is incomplete"):
        module.copy_reviewed_notice_files(entry, output)


@pytest.mark.parametrize("problem", ["pending", "version", "missing", "changed"])
def test_unreviewed_windows_native_closure_prevents_distribution(runtime, problem):
    module, manifest, _, output = runtime
    payload = module.DIST / "_internal" / "example.dll"
    if problem == "pending":
        manifest["windows_review_status"] = "pending"
    elif problem == "version":
        manifest["python_version"] = "3.14.7"
    elif problem == "missing":
        payload.rename(payload.with_suffix(".unavailable"))
    else:
        payload.write_bytes(b"different build")
    with pytest.raises(SystemExit):
        module.copy_windows_runtime_notices(output)
    assert not output.exists()


def test_reviewed_native_payload_receives_its_notice_tree(runtime):
    module, _, _, output = runtime
    rows = module.copy_windows_runtime_notices(output)
    assert rows[0][:3] == ("Example", "1.0", "MIT")
    assert (output / "example" / "dependency" / "LICENSE").read_text() == "Complete dependency terms"


@pytest.mark.parametrize("name", ["libportaudio64bit-asio.dll", "LIBPORTAUDIO32BIT-ASIO.DLL"])
def test_asio_binary_is_rejected_even_if_a_build_hook_reintroduces_it(runtime, name):
    module, _, _, _ = runtime
    (module.DIST / "_internal" / name).write_bytes(b"binary fixture")
    with pytest.raises(SystemExit, match="Excluded ASIO library"):
        module.verify_media_policy(module.DIST)
