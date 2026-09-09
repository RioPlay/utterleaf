from utterleaf.offline import apply_offline_defaults


def test_privacy_defaults_override_inherited_telemetry_and_implicit_auth(monkeypatch):
    import os
    keys = ["HF_HUB_DISABLE_TELEMETRY", "HF_HUB_DISABLE_IMPLICIT_TOKEN", "DO_NOT_TRACK"]
    for key in keys:
        monkeypatch.setenv(key, "0")
    apply_offline_defaults()
    assert all(os.environ[key] == "1" for key in keys)
