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


def test_platform_fallback_requires_exact_version_and_native_target(runtime, monkeypatch):
    module, manifest, entry, output = runtime
    manifest["packages"].pop("example")
    manifest["package_variants"] = {
        "example": {"1.0": {"linux:x86_64": entry}}
    }
    module.sys.platform = "linux"
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")
    module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output)
    assert (output / "LICENSE").read_text() == "Complete primary terms"

    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    with pytest.raises(SystemExit, match="full license text unavailable"):
        module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output / "wrong-arch")
    with pytest.raises(SystemExit, match="full license text unavailable"):
        module.copy_license_files(
            module.SITE / "example.dist-info", package_metadata(version="1.1"), output / "wrong-version"
        )


def test_target_restriction_prevents_reusing_a_platform_specific_review(runtime, monkeypatch):
    module, _, entry, output = runtime
    entry["targets"] = ["win32:x86_64"]
    module.sys.platform = "darwin"
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    with pytest.raises(SystemExit, match="full license text unavailable"):
        module.copy_license_files(module.SITE / "example.dist-info", package_metadata(), output)


def test_platform_review_binds_source_hash_and_packaged_native_inventory(runtime, monkeypatch):
    module, _, entry, _ = runtime
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    source = module.SITE / "example" / "native.so"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reviewed native input")
    packaged = module.DIST / "_internal" / "example" / "native.so"
    packaged.parent.mkdir(parents=True, exist_ok=True)
    packaged.write_bytes(b"possibly transformed packaged input")
    entry["payload_reviews"] = {"win32:x86_64": {
        "source_files": {"example/native.so": hashlib.sha256(source.read_bytes()).hexdigest()},
        "packaged_roots": ["example"],
        "packaged_native_files": ["example/native.so"],
    }}
    module.verify_reviewed_package_payload(entry)

    source.write_bytes(b"changed native input")
    with pytest.raises(SystemExit, match="unreviewed package native payload"):
        module.verify_reviewed_package_payload(entry)
    source.write_bytes(b"reviewed native input")
    (packaged.parent / "unexpected.dylib").write_bytes(b"unexpected")
    with pytest.raises(SystemExit, match="does not match its reviewed inventory"):
        module.verify_reviewed_package_payload(entry)
    (packaged.parent / "unexpected.dylib").unlink()

    module.sys.platform = "linux"
    with pytest.raises(SystemExit, match="native payload target has no completed review"):
        module.verify_reviewed_package_payload(entry)


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


def test_checked_in_ct2_platform_reviews_have_verified_distinct_closures(tmp_path):
    source = Path(__file__).resolve().parents[1] / "packaging" / "collect_notices.py"
    spec = importlib.util.spec_from_file_location("checked_in_runtime_notices", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    variants = module.runtime_notice_manifest()["package_variants"]["ctranslate2"]["4.8.2"]

    linux = tmp_path / "linux"
    module.copy_reviewed_notice_files(variants["linux:x86_64"], linux)
    assert (linux / "native" / "libgomp" / "COPYING3").is_file()
    assert (linux / "native" / "libgomp" / "COPYING.RUNTIME").is_file()
    assert (linux / "native" / "oneDNN-v3.1.1-LICENSE.txt").is_file()

    macos = tmp_path / "macos"
    module.copy_reviewed_notice_files(variants["darwin:arm64"], macos)
    assert (macos / "ruy" / "cpuinfo" / "LICENSE").is_file()
    assert not (macos / "native" / "libgomp").exists()
    assert not (macos / "native" / "oneDNN-v3.1.1-LICENSE.txt").exists()


def test_general_windows_ci_uses_the_reviewed_runtime_inputs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    lock = (root / "packaging" / "requirements-windows-preview.txt").read_text(encoding="utf-8")
    manifest = json.loads(
        (root / "packaging" / "notices" / "runtime-manifest.json").read_text(encoding="utf-8")
    )

    assert 'python-version: "3.14.6"' in workflow
    assert "pip install --require-hashes -r packaging\\requirements-windows-preview.txt" in workflow
    assert "pip install --no-deps --no-build-isolation -e ." in workflow
    assert "ctranslate2==4.8.1" in lock
    assert manifest["packages"]["ctranslate2"]["targets"] == ["win32:x86_64"]


def test_posix_ci_uses_the_reviewed_tokenizers_source_and_targets():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    constraints = [line.strip() for line in
                   (root / "packaging" / "constraints-posix.txt").read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")]
    manifest = json.loads(
        (root / "packaging" / "notices" / "runtime-manifest.json").read_text(encoding="utf-8")
    )

    assert workflow.count("--constraint packaging/constraints-posix.txt") == 4
    assert constraints == [
        "ctranslate2==4.8.2",
        "faster-whisper==1.2.1",
        "onnxruntime==1.28.0",
        "tokenizers==0.23.1",
    ]
    assert manifest["packages"]["tokenizers"]["targets"] == [
        "darwin:arm64", "linux:x86_64", "win32:x86_64",
    ]
    assert set(manifest["packages"]["tokenizers"]["payload_reviews"]) == {
        "darwin:arm64", "linux:x86_64", "win32:x86_64",
    }

    tokenizers = manifest["packages"]["tokenizers"]
    provenance_item = next(item for item in tokenizers["files"]
                           if item["path"] == "runtime/tokenizers/wheel-provenance.json")
    provenance_path = root / "packaging" / "notices" / provenance_item["path"]
    assert hashlib.sha256(provenance_path.read_bytes()).hexdigest() == provenance_item["sha256"]
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for target, review in tokenizers["payload_reviews"].items():
        wheel = provenance["targets"][target]
        assert review["source_files"] == {wheel["native_file"]: wheel["native_sha256"]}
        assert review["packaged_native_files"] == list(review["source_files"])


def test_checked_in_onnxruntime_reviews_bind_each_wheel_notice_and_native_payload():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "packaging" / "notices" / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    variants = manifest["package_variants"]["onnxruntime"]["1.28.0"]
    assert set(variants) == {"darwin:arm64", "linux:x86_64", "win32:x86_64"}
    assert "onnxruntime/capi/libonnxruntime.so.1.28.0" in (
        variants["linux:x86_64"]["payload_review"]["source_files"]
    )

    for target, entry in variants.items():
        review = entry["payload_review"]
        assert set(review["packaged_native_files"]) <= set(review["source_files"])
        assert review["packaged_roots"] == ["onnxruntime"]
        provenance_item = next(item for item in entry["files"]
                               if item["path"] == "runtime/onnxruntime/wheel-provenance.json")
        provenance_path = root / "packaging" / "notices" / provenance_item["path"]
        assert hashlib.sha256(provenance_path.read_bytes()).hexdigest() == provenance_item["sha256"]
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))["targets"][target]
        assert review["source_files"] == provenance["native_files"]
        assert review["packaged_native_files"] == provenance["expected_packaged_native_files"]
        site_files = {item["path"]: item["sha256"] for item in entry["files"]
                      if item.get("source_root") == "site"}
        assert site_files == provenance["notice_files"]
    assert "onnxruntime/capi/libonnxruntime.so.1.28.0" not in (
        variants["linux:x86_64"]["payload_review"]["packaged_native_files"]
    )
