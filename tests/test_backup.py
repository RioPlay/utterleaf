import json
from dataclasses import asdict

import pytest

from utterleaf.backup import (
    BackupError, BackupPlan, MAX_BACKUP_BYTES, MAX_VOCABULARY_ENTRIES,
    PORTABLE_PREFERENCES, export_backup, inspect_backup, merge_backup,
)
from utterleaf.config import Config


def document(**changes):
    value = json.loads(export_backup(Config(), ""))
    value.update(changes)
    return json.dumps(value)


def test_export_allowlist_excludes_private_and_machine_state():
    cfg = Config(microphone="Private USB microphone", hotkey="f8", model="C:/private/model",
                 allow_network=False, restore_clipboard=True, live_preview=True)
    cfg.control_token = "synthetic-secret"
    payload = export_backup(cfg, "# private comment\nutter leaf = Utterleaf\n")
    data = json.loads(payload)
    assert set(data["preferences"]) == set(PORTABLE_PREFERENCES)
    for private in ("microphone", "hotkey", "model", "allow_network", "restore_clipboard",
                    "live_preview", "control_token", "synthetic-secret", "private comment"):
        assert private not in payload
    assert data["vocabulary"] == [{"spoken": "utter leaf", "written": "Utterleaf"}]


def test_unicode_round_trip_and_review_make_no_mutations():
    original = Config(allow_network=False, restore_clipboard=True, beep=True, live_preview=False)
    before = asdict(original)
    plan = inspect_backup(export_backup(Config(beep=False), "cafe = Café\n名 = 名前\n").encode())
    result = merge_backup(plan, original, "# retained\nexisting = Existing\n")
    assert asdict(result.config) == before
    assert result.vocabulary_text == "# retained\nexisting = Existing\n"
    assert asdict(original) == before
    selected = merge_backup(plan, original, result.vocabulary_text,
                            preference_keys=["beep"], vocabulary_mode="merge")
    assert selected.config.beep is False
    assert selected.config.allow_network is False
    assert selected.config.restore_clipboard is True
    assert selected.config.live_preview is False
    assert selected.vocabulary_text.endswith("cafe = Café\n名 = 名前\n")
    assert asdict(original) == before


def test_markdown_output_preference_is_portable_and_explicitly_applied():
    plan = inspect_backup(export_backup(Config(output_format="markdown"), ""))
    assert dict(plan.preferences)["output_format"] == "markdown"
    merged = merge_backup(plan, Config(), "", preference_keys=["output_format"])
    assert merged.config.output_format == "markdown"


def test_backup_rejects_unknown_output_style():
    with pytest.raises(BackupError):
        inspect_backup(document(preferences={"output_format": "cloud"}))


def test_speech_end_preferences_are_portable_and_strict():
    cfg = Config(speech_end_enabled=True, speech_end_pause_seconds=1.8, speech_end_insert=True)
    plan = inspect_backup(export_backup(cfg, ""))
    preferences = dict(plan.preferences)
    assert preferences["speech_end_enabled"] is True
    assert preferences["speech_end_pause_seconds"] == 1.8
    assert preferences["speech_end_insert"] is True
    with pytest.raises(BackupError):
        inspect_backup(document(preferences={"speech_end_pause_seconds": 9}))
    with pytest.raises(BackupError):
        inspect_backup(document(preferences={"speech_end_insert": "yes"}))


def test_explicit_merge_preserves_existing_definitions_comments_and_reports_conflicts():
    plan = inspect_backup(export_backup(Config(), "NAME = Imported\nnew = New\n"))
    current = "# keep this comment\nname = Original"  # No trailing newline.
    result = merge_backup(plan, Config(), current, vocabulary_mode="merge")
    assert result.vocabulary_text == current + "\nnew = New\n"
    assert result.vocabulary_conflicts == ("NAME",)
    replaced = merge_backup(plan, Config(), current, vocabulary_mode="replace")
    assert replaced.vocabulary_text == "NAME = Imported\nnew = New\n"


def test_omitted_and_empty_vocabulary_are_distinct():
    omitted = inspect_backup(export_backup(Config(), "", include_vocabulary=False))
    assert omitted.vocabulary is None
    with pytest.raises(BackupError):
        merge_backup(omitted, Config(), "a = A", vocabulary_mode="replace")
    empty = inspect_backup(export_backup(Config(), ""))
    assert merge_backup(empty, Config(), "a = A", vocabulary_mode="replace").vocabulary_text == ""


@pytest.mark.parametrize("change", [
    {"version": 2}, {"version": True}, {"format": "other"}, {"path": "../../config.toml"},
    {"preferences": {"allow_network": True}}, {"preferences": {"restore_clipboard": False}},
    {"preferences": {"live_preview": True}}, {"preferences": {"microphone": "private"}},
    {"preferences": {"beep": 1}}, {"preferences": {"beep": "false"}},
    {"preferences": {"denoise": "../path"}}, {"preferences": []},
    {"vocabulary": {}}, {"vocabulary": [{"spoken": "a", "written": "b", "path": "../x"}]},
    {"vocabulary": [{"spoken": "#comment", "written": "b"}]},
    {"vocabulary": [{"spoken": "a=b", "written": "c"}]},
    {"vocabulary": [{"spoken": "a", "written": "new\nline"}]},
    {"vocabulary": [{"spoken": "a", "written": "value\u2028injected = replacement"}]},
    {"vocabulary": [{"spoken": "a", "written": "value\u2029injected = replacement"}]},
    {"vocabulary": [{"spoken": "a", "written": "hidden\u202etext"}]},
    {"vocabulary": [{"spoken": "a", "written": "\ud800"}]},
    {"vocabulary": [{"spoken": "a", "written": " "}]},
    {"vocabulary": [{"spoken": "a", "written": "b"}, {"spoken": "A", "written": "c"}]},
])
def test_rejects_malicious_or_invalid_schema(change):
    with pytest.raises(BackupError):
        inspect_backup(document(**change))


@pytest.mark.parametrize("payload", [b"\xff", "{", "[]", "null", "[" * 2000,
                                      '{"version":1,"version":1}', document().replace('true', 'NaN', 1)])
def test_malformed_json_fails_closed_without_echoing_payload(payload):
    with pytest.raises(BackupError) as error:
        inspect_backup(payload)
    assert len(str(error.value)) < 100


def test_byte_entry_and_term_limits():
    with pytest.raises(BackupError):
        inspect_backup(b" " * (MAX_BACKUP_BYTES + 1))
    with pytest.raises(BackupError):
        export_backup(Config(), "a = " + "x" * 257)
    oversized = [dict(spoken=str(i), written="word") for i in range(MAX_VOCABULARY_ENTRIES + 1)]
    with pytest.raises(BackupError):
        inspect_backup(document(vocabulary=oversized))
    with pytest.raises(BackupError):
        export_backup(Config(), "#" + "界" * (256 * 1024 // 3 + 1))


def test_combined_merge_limit_is_checked_before_returning_candidates():
    current = "".join(f"word{i} = value\n" for i in range(MAX_VOCABULARY_ENTRIES))
    plan = inspect_backup(export_backup(Config(beep=False), "additional = Value"))
    cfg = Config(beep=True)
    with pytest.raises(BackupError):
        merge_backup(plan, cfg, current, vocabulary_mode="merge", preference_keys=["beep"])
    assert cfg.beep is True


def test_inspection_never_interprets_a_path_or_overwrites_live_files(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    vocabulary = tmp_path / "dictionary.txt"
    config.write_text("sentinel config", encoding="utf-8")
    vocabulary.write_text("sentinel vocabulary", encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Backup preview must not open files")
    with monkeypatch.context() as patch:
        patch.setattr("builtins.open", forbidden)
        patch.setattr("pathlib.Path.open", forbidden)
        with pytest.raises(BackupError):
            inspect_backup(str(config))
        plan = inspect_backup(export_backup(Config(beep=False), "a = A"))
        merge_backup(plan, Config(), "b = B", vocabulary_mode="replace", preference_keys=["beep"])
        with pytest.raises(BackupError):
            inspect_backup(document(path=str(config)))
    assert config.read_text() == "sentinel config"
    assert vocabulary.read_text() == "sentinel vocabulary"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["config.toml", "dictionary.txt"]


def test_explicit_selection_and_forged_plan_cannot_import_protected_fields():
    plan = inspect_backup(export_backup(Config(), "", preference_keys=["beep"]))
    for keys in (["allow_network"], ["tray"], ["beep", "beep"], "beep"):
        with pytest.raises(BackupError):
            merge_backup(plan, Config(), "", preference_keys=keys)
    with pytest.raises(BackupError):
        merge_backup(BackupPlan((("allow_network", True),), ()), Config(), "")
    with pytest.raises(BackupError):
        merge_backup(plan, Config(), "", vocabulary_mode="automatic")
    with pytest.raises(BackupError):
        export_backup(Config(), "bad line")
    with pytest.raises(BackupError):
        export_backup(Config(), "", preference_keys=["hotkey"])
