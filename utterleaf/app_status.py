"""Fixed, text-free app presentation status shared by the tray and Settings.

These are last-checked states, not a continuous device monitor. Ready additionally
requires the app's nonblocking proof of a matching, successfully loaded engine.
Keep this module independent of audio, models, configuration, and UI imports.
"""

from utterleaf.model_presentation import PUBLIC_MODEL_TOKENS, model_display_name


_SNAPSHOT_STATES = frozenset({"idle", "ready", "listening", "processing", "attention", "unknown"})
_CONFIRMED_MODELS = PUBLIC_MODEL_TOKENS | {"custom"}
_SNAPSHOT_MODELS = _CONFIRMED_MODELS | {"unconfirmed"}
_SNAPSHOT_LIMIT = len("status-v2::") + max(map(len, _SNAPSHOT_STATES)) + max(map(len, _SNAPSHOT_MODELS))


def presentation_reply(color: str) -> str:
    state = {"idle": "idle", "recording": "listening", "busy": "processing",
             "error": "attention"}.get(color, "unknown")
    return f"status-v1:{state}"


def status_message(reply: str | None) -> str:
    """Accept only known tokens; never render arbitrary local-server output."""
    messages = {
        "status-v1:idle": "Idle · app is running",
        "status-v1:ready": "Ready · applied speech model loaded",
        "status-v1:listening": "Listening · speech capture in progress",
        "status-v1:processing": "Processing · preparing or transcribing speech",
        "status-v1:attention": "Needs attention · check the tray or open Help",
        "status-v1:unknown": "App is running · detailed status unavailable",
        # Older authenticated instances do not implement the status command.
        "unknown": "App is running · detailed status unavailable in this version",
        "restart-required": "Restart Utterleaf to check its status",
        None: "App not reached · Start Utterleaf, then refresh status",
    }
    return messages.get(reply, "Could not read app status · restart Utterleaf, then retry")


def snapshot_reply(state: str, model: str | None) -> str:
    """Encode fixed public tokens; never turn absent load proof into Ready."""
    state = state if type(state) is str and state in _SNAPSHOT_STATES else "unknown"
    model = model if type(model) is str and model in _CONFIRMED_MODELS else "unconfirmed"
    if state == "ready" and model == "unconfirmed":
        state = "idle"
    return f"status-v2:{state}:{model}"


def snapshot_message(reply: str | None) -> str | None:
    """Parse the exact bounded v2 grammar, then render only fixed local copy.

    No trimming, case conversion or arbitrary identifier display is permitted.
    Invalid/non-v2 input returns None so the caller can choose safe recovery;
    it must not use malformed data as a signal to query an older protocol.
    """
    if type(reply) is not str or len(reply) > _SNAPSHOT_LIMIT:
        return None
    parts = reply.split(":")
    if len(parts) != 3:
        return None
    version, state, model = parts
    if version != "status-v2" or state not in _SNAPSHOT_STATES or model not in _SNAPSHOT_MODELS:
        return None
    if state == "ready" and model == "unconfirmed":
        return None
    name = "not confirmed" if model == "unconfirmed" else model_display_name(model)
    return f"{status_message('status-v1:' + state)}\nLoaded model for applied settings: {name}."
