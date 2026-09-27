"""Read-only model inventory against temporary stores, never personal models."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from utterleaf import model_inventory as inventory, model_setup, models
from utterleaf.hardware import ov_model_id


NAMES = ("tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
         "medium.en", "large-v3", "distil-small.en")
PAIRS = tuple((name, backend) for name in NAMES
              for backend in (("ctranslate2", "openvino") if ov_model_id(name) else ("ctranslate2",)))


def blocked(*_args, **_kwargs):
    pytest.fail("Inventory must not perform an external or mutating operation")


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "models_dir", lambda: tmp_path)
    for target in (
        "utterleaf.config.save", "utterleaf.models.ensure_ct2", "utterleaf.models.ensure_ov",
        "utterleaf.model_setup.download_selected", "utterleaf.model_setup.run_download",
        "utterleaf.hardware.probe", "utterleaf.hardware.pick", "utterleaf.hardware.openvino_devices",
        "socket.socket", "socket.create_connection", "subprocess.Popen",
    ):
        monkeypatch.setattr(target, blocked)
    return tmp_path


def folder_for(name="tiny", backend="ctranslate2"):
    return models.ct2_dir(name) if backend == "ctranslate2" else models.ov_dir(ov_model_id(name))


def install(name="tiny", backend="ctranslate2", vocabulary="vocabulary.txt"):
    folder = folder_for(name, backend)
    folder.mkdir(parents=True)
    filenames = ((*model_setup.CT2_REQUIRED, vocabulary) if backend == "ctranslate2"
                 else model_setup.OV_REQUIRED)
    total = 0
    for filename in filenames:
        data = b'["word"]' if filename == "vocabulary.json" else b"{}" if filename.endswith(".json") else b"fixture"
        (folder / filename).write_bytes(data)
        total += len(data)
    return folder, total


def test_missing_store_is_empty_and_is_not_created(isolated_store, monkeypatch):
    missing = isolated_store / "does-not-exist"
    monkeypatch.setattr(models, "models_dir", lambda: missing)
    monkeypatch.setattr(inventory, "inspect_model", blocked)
    assert inventory.inventory_models() == ()
    assert not missing.exists()


def test_all_sixteen_guided_pairs_use_stable_size_order_and_backend_separation():
    assert len(PAIRS) == 16
    sizes = {(name, backend): install(name, backend)[1] for name, backend in reversed(PAIRS)}
    rows = inventory.inventory_models()
    assert isinstance(rows, tuple)
    assert [(row.name, row.backend) for row in rows] == list(PAIRS)
    for row in rows:
        assert row.state == "installed" and row.detail == ""
        assert row.size_bytes == sizes[row.name, row.backend]
    with pytest.raises(FrozenInstanceError):
        rows[0].state = "ready"


@pytest.mark.parametrize("backend", ["ctranslate2", "openvino"])
def test_only_the_present_backend_is_reported(backend):
    _, size = install("tiny.en", backend)
    assert inventory.inventory_models() == (
        inventory.ModelInstallation("tiny.en", backend, "installed", size),
    )


def test_empty_existing_installation_is_incomplete_with_truthful_zero():
    folder_for().mkdir()
    assert inventory.inventory_models() == (
        inventory.ModelInstallation("tiny", "ctranslate2", "incomplete", 0),
    )


def test_incomplete_installation_counts_remaining_known_files():
    folder = folder_for()
    folder.mkdir()
    (folder / "model.bin").write_bytes(b"partial weights")
    (folder / "config.json").write_bytes(b"{}")
    assert inventory.inventory_models() == (
        inventory.ModelInstallation("tiny", "ctranslate2", "incomplete", 17),
    )


@pytest.mark.parametrize("vocabulary", ["vocabulary.txt", "vocabulary.json", "both"])
def test_valid_vocabulary_alternatives_and_both_files_count(vocabulary):
    folder, size = install(vocabulary="vocabulary.json" if vocabulary == "vocabulary.json" else "vocabulary.txt")
    if vocabulary == "both":
        (folder / "vocabulary.json").write_bytes(b'["extra"]')
        size += len(b'["extra"]')
    row, = inventory.inventory_models()
    assert row.state == "installed" and row.size_bytes == size and not row.detail


@pytest.mark.parametrize("filename,data", [
    ("config.json", b"not JSON"),
    ("tokenizer.json", b"[]"),
    ("vocabulary.json", b"not JSON"),
    ("model.bin", b""),
])
def test_invalid_setup_content_is_incomplete_but_size_remains_measurable(filename, data):
    folder, size = install(vocabulary="vocabulary.json")
    previous = (folder / filename).stat().st_size
    (folder / filename).write_bytes(data)
    row, = inventory.inventory_models()
    assert row.state == "incomplete"
    assert row.size_bytes == size - previous + len(data)
    assert row.detail == ""


def test_unknown_models_hub_and_extra_files_are_not_enumerated_or_counted(isolated_store, monkeypatch):
    folder, size = install()
    (folder / "unrecognized.bin").write_bytes(b"extra" * 100)
    (folder / "nested").mkdir()
    (folder / "nested" / "model.bin").write_bytes(b"nested" * 100)
    (isolated_store / "hub").mkdir()
    (isolated_store / "hub" / "cached.bin").write_bytes(b"shared" * 100)
    (isolated_store / "faster-whisper-private-model").mkdir()
    for name in ("glob", "rglob", "iterdir", "mkdir", "unlink", "rmdir", "rename", "replace", "write_bytes", "write_text"):
        monkeypatch.setattr(Path, name, blocked)
    assert inventory.inventory_models() == (
        inventory.ModelInstallation("tiny", "ctranslate2", "installed", size),
    )


@pytest.mark.parametrize("point", ["directory", "file_stat", "file_open", "inspection"])
def test_per_entry_io_failure_has_unknown_size_and_does_not_hide_other_models(monkeypatch, point):
    folder, _ = install()
    _, later_size = install("base")
    original_stat, original_open, original_inspect = Path.stat, Path.open, inventory.inspect_model
    error = PermissionError("private test path is inaccessible")

    def checked_stat(path, *args, **kwargs):
        if path == (folder if point == "directory" else folder / "model.bin"):
            raise error
        return original_stat(path, *args, **kwargs)

    def checked_open(path, *args, **kwargs):
        if path == folder / "model.bin":
            raise error
        return original_open(path, *args, **kwargs)

    def checked_inspect(name, backend):
        if name == "tiny" and backend == "ctranslate2":
            raise error
        return original_inspect(name, backend)

    if point in {"directory", "file_stat"}:
        monkeypatch.setattr(Path, "stat", checked_stat)
    elif point == "file_open":
        monkeypatch.setattr(Path, "open", checked_open)
    else:
        monkeypatch.setattr(inventory, "inspect_model", checked_inspect)
    first, second = inventory.inventory_models()
    assert first == inventory.ModelInstallation("tiny", "ctranslate2", "error", None, str(error))
    assert second == inventory.ModelInstallation("base", "ctranslate2", "installed", later_size)


@pytest.mark.parametrize("change", ["remove_file", "change_file", "add_file", "remove_folder", "missing_result"])
def test_changes_during_inspection_retain_an_error_row(monkeypatch, change):
    folder, _ = install()
    original = inventory.inspect_model

    def inspect(name, backend):
        result = original(name, backend)
        if name == "tiny" and backend == "ctranslate2":
            if change == "remove_file":
                (folder / "model.bin").unlink()
            elif change == "change_file":
                (folder / "model.bin").write_bytes(b"changed weight length")
            elif change == "add_file":
                (folder / "vocabulary.json").write_bytes(b"[]")
            elif change == "remove_folder":
                for filename in (*model_setup.CT2_REQUIRED, "vocabulary.txt"):
                    (folder / filename).unlink()
                folder.rmdir()
            else:
                return replace(result, state="missing")
        return result

    monkeypatch.setattr(inventory, "inspect_model", inspect)
    row, = inventory.inventory_models()
    assert row.name == "tiny" and row.backend == "ctranslate2"
    assert row.state == "error" and row.size_bytes is None and row.detail


def test_known_filename_directory_is_not_counted_as_file_bytes():
    folder = folder_for()
    folder.mkdir()
    (folder / "model.bin").mkdir()
    row, = inventory.inventory_models()
    assert row.state == "incomplete" and row.size_bytes == 0


def test_expected_model_directory_that_is_a_file_is_an_error():
    folder_for().write_bytes(b"not a directory")
    row, = inventory.inventory_models()
    assert row.state == "error" and row.size_bytes is None
    assert "not a directory" in row.detail


@pytest.mark.parametrize("exception", [RuntimeError("unexpected bug"), TypeError("unexpected type")])
def test_unexpected_inspector_errors_propagate_to_controller(monkeypatch, exception):
    install()

    def fail(*_args):
        raise exception

    monkeypatch.setattr(inventory, "inspect_model", fail)
    with pytest.raises(type(exception), match=str(exception)):
        inventory.inventory_models()


def test_unexpected_guided_state_is_not_silently_omitted(monkeypatch):
    folder, _ = install()
    monkeypatch.setattr(inventory, "inspect_model", lambda name, backend:
                        model_setup.ModelAvailability(name, backend, "unsupported", folder))
    with pytest.raises(ValueError, match="Unexpected state"):
        inventory.inventory_models()
