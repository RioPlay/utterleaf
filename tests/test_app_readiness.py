"""Applied-model readiness without microphone, model, network, or GUI work."""

from dataclasses import replace
import threading
from types import SimpleNamespace

import pytest

from utterleaf import app as app_module
from utterleaf.app import DOWNLOADING, ENGINE_FAILED
from test_app import _app


class _Indicator:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.calls = []
        self.closed = False

    def start(self):
        pass

    def close(self):
        self.closed = True

    def set(self, badge, caption=""):
        self.calls.append((badge, caption))


@pytest.fixture
def model_app(monkeypatch):
    app = _app(monkeypatch, model="tiny", device="cpu", allow_network=False)
    app.indicator = _Indicator()
    workers = []
    calls = []
    cache = {"ready": False}
    chosen = SimpleNamespace(backend="ct2")

    class DeferredThread:
        def __init__(self, *, target, args=(), kwargs=None, **_options):
            self.target, self.args, self.kwargs = target, args, kwargs or {}

        def start(self):
            workers.append(self)

        def run(self):
            self.target(*self.args, **self.kwargs)

    def load(cfg, selected):
        calls.append(("load", cfg, selected))
        cache["ready"] = True

    def reset():
        calls.append(("reset",))
        cache["ready"] = False

    monkeypatch.setattr(app_module, "threading", SimpleNamespace(
        Thread=DeferredThread, Event=threading.Event, Timer=threading.Timer,
    ))
    monkeypatch.setattr(app_module, "pick", lambda cfg: calls.append(("pick", cfg)) or chosen)
    monkeypatch.setattr(app_module, "load_model", load)
    monkeypatch.setattr(app_module, "reset_engine", reset)
    monkeypatch.setattr(app_module, "engine_ready", lambda cfg: cache["ready"])
    monkeypatch.setattr(app_module, "clear_final", lambda: None)
    monkeypatch.setattr(app_module.ipc, "clear", lambda: None)
    monkeypatch.setattr(app, "_needs_download", lambda selected, cfg=None: False)
    return SimpleNamespace(app=app, workers=workers, calls=calls, cache=cache, chosen=chosen)


@pytest.fixture
def result_timers(model_app, monkeypatch):
    timers = []

    class DeferredTimer:
        def __init__(self, seconds, callback):
            self.seconds, self.callback = seconds, callback
            self.cancelled = False

        def start(self):
            timers.append(self)

        def cancel(self):
            self.cancelled = True

        def fire(self):
            self.callback()

    monkeypatch.setattr(app_module.threading, "Timer", DeferredTimer)
    return timers


def _presentation(app):
    return (app._status, app._display_color, app._display_badge,
            app._display_caption, app._reported_status)


def _activity(app, activity):
    if activity == "loading":
        return
    if activity == "opening":
        app.state = "recording"
        app._set_icon("busy", "opening microphone", badge="loading", caption="Opening input")
    elif activity == "listening":
        app.state = "recording"
        app._set_icon("recording", "listening", badge="listening", caption="Listening caption")
    elif activity == "queued":
        app.state = "busy"
        app._job_running = True
        app._set_icon("busy", "finishing queued dictation", badge="transcribing")
    elif activity == "tail":
        app._tail_timer = SimpleNamespace(cancel=lambda: None)
        app._set_icon("busy", "finishing recording", badge="transcribing")
    elif activity == "error":
        app._show_error("no_mic", "microphone unavailable", "Retry input", seconds=None)
    elif activity == "result":
        app._set_icon("idle", "Inserted", badge="pasted", caption="Completed result")
    else:
        raise AssertionError(activity)


def test_public_startup_uses_shared_deferred_model_warmup(model_app, monkeypatch):
    app = model_app.app
    startup_calls = []
    warmup = app._start_model_warmup

    def start_warmup(**options):
        startup_calls.append(options)
        warmup(**options)

    monkeypatch.setattr(app, "_start_model_warmup", start_warmup)
    monkeypatch.setattr(app, "_ensure_endpoint_detector", lambda: None)
    monkeypatch.setattr(app_module.ipc, "send", lambda command: None)
    monkeypatch.setattr(app_module.ipc, "bind", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(app_module, "HotkeyWatcher", lambda *args, **kwargs: SimpleNamespace(
        start=app._stop.set, stop=lambda: None,
    ))

    app.run()

    assert startup_calls == [{}]
    assert [worker.target.__name__ for worker in model_app.workers] == ["_ipc_loop", "_warm_model"]
    assert app._model_generation == 1
    assert app._model_phase == "loading"
    assert model_app.calls == []


def test_warmup_freezes_config_for_selection_download_check_and_load(model_app, monkeypatch):
    app = model_app.app
    app.cfg.allow_network = True
    original = replace(app.cfg)
    probed = []

    def needs_download(chosen, cfg=None):
        probed.append((chosen, cfg))
        return True

    monkeypatch.setattr(app, "_needs_download", needs_download)
    app._start_model_warmup(reset=True)
    app.cfg.model = "medium"
    app.cfg.language = "ja"
    app.cfg.device = "gpu"
    app.cfg.compute_type = "float16"
    app.cfg.allow_network = False

    model_app.workers[0].run()

    selected_cfg = model_app.calls[1][1]
    loaded_cfg = model_app.calls[2][1]
    assert model_app.calls[0] == ("reset",)
    assert selected_cfg == original
    assert loaded_cfg == replace(original, allow_network=False)
    assert selected_cfg is not app.cfg and loaded_cfg is not app.cfg
    assert probed == [(model_app.chosen, selected_cfg)]
    assert ("loading", DOWNLOADING) not in app.indicator.calls


@pytest.mark.parametrize("backend", ["ct2", "openvino"])
def test_download_probe_uses_supplied_frozen_model_config(model_app, monkeypatch, backend):
    app = model_app.app
    frozen = replace(app.cfg)
    app.cfg.model = "medium"
    probed = []
    monkeypatch.setattr(app_module, "resolve_name", lambda cfg: cfg.model)
    monkeypatch.setattr(app_module, "ct2_dir", lambda name: ("ct2", name))
    monkeypatch.setattr(app_module, "ct2_ready", lambda folder: probed.append(folder) or False)
    monkeypatch.setattr(app_module, "ov_model_id", lambda name: "ov-" + name)
    monkeypatch.setattr(app_module, "ov_dir", lambda repo: ("openvino", repo))
    monkeypatch.setattr(app_module, "ov_ready", lambda folder: probed.append(folder) or False)

    assert type(app)._needs_download(app, SimpleNamespace(backend=backend), frozen)
    assert probed == [(backend, "ov-tiny" if backend == "openvino" else "tiny")]


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_stale_completion_cannot_replace_new_generation_loading(model_app, monkeypatch, outcome):
    app = model_app.app
    app._start_model_warmup()
    generation = app._model_generation

    def finish_old(cfg, chosen):
        app.cfg = replace(app.cfg, model="base")
        app._start_model_warmup(reset=True)
        if outcome == "failure":
            raise RuntimeError("old model failed")

    monkeypatch.setattr(app_module, "load_model", finish_old)
    model_app.workers[0].run()

    assert app._model_generation == generation + 1
    assert app._model_phase == "loading"
    assert app._display_badge == "loading"
    assert app._handle_ipc("status") == "status-v1:processing"
    assert len(model_app.workers) == 2

    monkeypatch.setattr(app_module, "load_model", lambda *args: model_app.cache.update(ready=True))
    model_app.workers[1].run()
    assert app._model_phase == "ready"
    assert app._handle_ipc("status") == "status-v1:ready"


@pytest.mark.parametrize("replacement", ["new_generation", "quit"])
def test_waiting_worker_rechecks_generation_and_quit_after_entering_lane(model_app, replacement):
    app = model_app.app
    app._start_model_warmup(reset=True)

    class ChangedWhileWaiting:
        def __enter__(self):
            if replacement == "new_generation":
                app._start_model_warmup(reset=True)
            else:
                app.quit()

        def __exit__(self, *_args):
            return False

    app._model_load_lock = ChangedWhileWaiting()
    before = _presentation(app)
    model_app.workers[0].run()

    assert model_app.calls == []
    assert app._model_phase == "loading"
    assert _presentation(app) == before


@pytest.mark.parametrize("activity", ["opening", "listening", "queued", "tail", "error", "result"])
@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_current_model_result_preserves_active_presentation(model_app, monkeypatch, activity, outcome):
    app = model_app.app
    app.cfg.allow_network = True
    monkeypatch.setattr(app, "_needs_download", lambda chosen, cfg=None: True)
    app._start_model_warmup()
    _activity(app, activity)
    before = _presentation(app)
    state_before = app.state

    if outcome == "failure":
        def fail(*args):
            raise RuntimeError("model unavailable")
        monkeypatch.setattr(app_module, "load_model", fail)

    model_app.workers[0].run()

    assert app._model_phase == ("ready" if outcome == "success" else "failed")
    assert app.state == state_before
    assert _presentation(app) == before


@pytest.mark.parametrize("activity", ["loading", "opening", "listening", "queued", "tail", "error", "result"])
def test_non_model_reload_preserves_current_presentation(model_app, monkeypatch, activity):
    app = model_app.app
    app._start_model_warmup()
    _activity(app, activity)
    before = _presentation(app)
    state_before = app.state
    generation = app._model_generation
    new_cfg = replace(app.cfg, text_cleanup=not app.cfg.text_cleanup)
    monkeypatch.setattr("utterleaf.config.load", lambda: new_cfg)

    app.reload_config()

    assert app.cfg is new_cfg
    assert app.state == state_before
    assert _presentation(app) == before
    assert app._model_generation == generation
    assert len(model_app.workers) == 1
    assert model_app.calls == []


@pytest.mark.parametrize("field,value", [
    ("model", "base"), ("device", "gpu"), ("language", "ja"), ("compute_type", "float16"),
])
def test_model_reload_schedules_new_generation_without_synchronous_model_work(model_app, monkeypatch, field, value):
    app = model_app.app
    app._start_model_warmup()
    original_worker = model_app.workers[0]
    original_generation = app._model_generation
    new_cfg = replace(app.cfg, **{field: value})
    monkeypatch.setattr("utterleaf.config.load", lambda: new_cfg)

    app.reload_config()

    assert app._model_generation == original_generation + 1
    assert app._model_phase == "loading"
    assert model_app.calls == []
    original_worker.run()
    assert model_app.calls == []
    assert model_app.workers[1].args == (app._model_generation, new_cfg, True)
    model_app.workers[1].run()
    assert [call[0] for call in model_app.calls] == ["reset", "pick", "load"]
    assert app._handle_ipc("status") == "status-v1:ready"


@pytest.mark.parametrize("phase,expected", [("loading", "loading"), ("failed", "engine"), ("ready", "hide")])
@pytest.mark.parametrize("job_running", [False, True])
def test_cancel_recording_restores_durable_model_phase(model_app, monkeypatch, phase, expected, job_running):
    app = model_app.app
    app._start_model_warmup()
    if phase == "failed":
        def fail(*args):
            raise RuntimeError("model unavailable")
        monkeypatch.setattr(app_module, "load_model", fail)
        model_app.workers[0].run()
    elif phase == "ready":
        model_app.workers[0].run()
    _activity(app, "listening")
    app.recorder.recording = True
    app._job_running = job_running
    cancelled_delivery = app._delivery_guard()

    app.cancel_recording()

    assert app.state == "idle"
    assert not app.recorder.recording
    assert app._job_running is job_running
    assert app._cancel_job is job_running
    assert app._model_phase == phase
    assert app._display_badge == expected
    expected_reply = {"failed": "status-v1:attention", "loading": "status-v1:processing", "ready": "status-v1:ready"}[phase]
    assert app._handle_ipc("status") == expected_reply
    assert cancelled_delivery()
    app._after_job()
    assert not app._job_running
    assert not app._cancel_job
    assert app._display_badge == expected
    assert app._handle_ipc("status") == expected_reply
    assert cancelled_delivery()


def test_idle_presentation_never_changes_capture_state(model_app):
    app = model_app.app
    app.state = "recording"
    app._idle_presentation()
    assert app.state == "recording"
    assert app._display_badge == "loading"


def test_failed_phase_can_recover_after_explicit_inference_proves_current_cache(model_app):
    app = model_app.app
    app._model_phase = "failed"
    app._idle()
    assert app._status == ENGINE_FAILED
    model_app.cache["ready"] = True
    app._idle()
    assert app._model_phase == "ready"
    assert app._handle_ipc("status") == "status-v1:ready"


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_quit_ignores_inflight_completion_and_new_warmups(model_app, monkeypatch, outcome):
    app = model_app.app
    app._start_model_warmup()
    before = _presentation(app)

    def load_then_quit(*args):
        app.quit()
        if outcome == "failure":
            raise RuntimeError("completion after quit")

    monkeypatch.setattr(app_module, "load_model", load_then_quit)
    model_app.workers[0].run()
    app._start_model_warmup(reset=True)

    assert app._stop.is_set()
    assert app.indicator.closed
    assert app._model_phase == "loading"
    assert _presentation(app) == before
    assert len(model_app.workers) == 1


def test_ready_query_rechecks_cache_for_applied_preferences_without_other_work(model_app, monkeypatch):
    app = model_app.app
    app._start_model_warmup()
    model_app.workers[0].run()
    assert app._handle_ipc("status") == "status-v1:ready"
    calls_before = list(model_app.calls)
    workers_before = list(model_app.workers)
    presentation_before = _presentation(app)
    seen = []
    applied = app.cfg

    def ready(cfg):
        seen.append(cfg)
        return model_app.cache["ready"]

    monkeypatch.setattr(app_module, "engine_ready", ready)
    model_app.cache["ready"] = False
    assert app._handle_ipc("status") == "status-v1:idle"
    model_app.cache["ready"] = True
    assert app._handle_ipc("status") == "status-v1:ready"
    assert seen == [applied, applied]
    assert all(cfg is applied for cfg in seen)
    assert model_app.calls == calls_before
    assert model_app.workers == workers_before
    assert _presentation(app) == presentation_before


def test_status_query_does_not_acquire_app_or_model_locks(model_app):
    app = model_app.app
    app._model_phase = "ready"
    model_app.cache["ready"] = True
    app._idle()
    replies = []
    finished = threading.Event()

    def query():
        replies.append(app._handle_ipc("status"))
        finished.set()

    worker = threading.Thread(target=query, daemon=True)
    with app._capture_lock, app._lock, app._presentation_lock, app._model_load_lock:
        worker.start()
        completed_while_locked = finished.wait(2)
    worker.join(2)
    assert completed_while_locked
    assert not worker.is_alive()
    assert replies == ["status-v1:ready"]


def test_native_load_holds_only_loading_lane_and_keeps_status_query_responsive(model_app, monkeypatch):
    app = model_app.app
    app._start_model_warmup()
    entered = threading.Event()
    release = threading.Event()

    def blocked_load(*args):
        entered.set()
        assert release.wait(2)
        model_app.cache["ready"] = True

    monkeypatch.setattr(app_module, "load_model", blocked_load)
    worker = threading.Thread(target=model_app.workers[0].run, daemon=True)
    worker.start()
    acquired = []
    try:
        assert entered.wait(2)
        for lock in (app._capture_lock, app._lock, app._presentation_lock):
            assert lock.acquire(timeout=0.2)
            acquired.append(lock)
        assert not app._model_load_lock.acquire(blocking=False)
        assert app._handle_ipc("status") == "status-v1:processing"
    finally:
        for lock in reversed(acquired):
            lock.release()
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert app._handle_ipc("status") == "status-v1:ready"


def test_reenabled_indicator_replays_opening_badge_without_claiming_listening(model_app, monkeypatch):
    app = model_app.app
    _activity(app, "opening")
    before = _presentation(app)
    previous = app.indicator
    monkeypatch.setattr(app_module, "Indicator", _Indicator)
    monkeypatch.setattr("utterleaf.config.load", lambda: replace(app.cfg, tray=True, indicator=True))

    app.reload_config()

    assert previous.closed
    assert app.indicator.enabled
    assert app.indicator.calls == [("loading", "Opening input")]
    assert _presentation(app) == before


@pytest.mark.parametrize("badge", ["too_short", "pasted", "missed"])
@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_result_expiry_restores_model_result_that_completed_during_linger(
    model_app, result_timers, monkeypatch, badge, outcome,
):
    app = model_app.app
    app._start_model_warmup()
    app._flash(badge, "Temporary result")
    assert app._display_badge == badge
    assert app._handle_ipc("status") == "status-v1:processing"
    if outcome == "failure":
        def fail(*args):
            raise RuntimeError("model unavailable")
        monkeypatch.setattr(app_module, "load_model", fail)

    model_app.workers[0].run()
    assert app._display_badge == badge
    result_timers[0].fire()

    assert app.state == "idle"
    assert app._display_badge == ("hide" if outcome == "success" else "engine")
    assert app._handle_ipc("status") == ("status-v1:ready" if outcome == "success" else "status-v1:attention")


@pytest.mark.parametrize("badge", ["too_short", "pasted", "missed"])
@pytest.mark.parametrize("phase", ["loading", "failed"])
def test_result_flash_preserves_unavailable_model_status_until_expiry(
    model_app, result_timers, badge, phase,
):
    app = model_app.app
    app._model_phase = phase
    app._idle()

    app._flash(badge, "Temporary result")

    expected = "status-v1:processing" if phase == "loading" else "status-v1:attention"
    assert app._display_badge == badge
    assert app._handle_ipc("status") == expected
    result_timers[0].fire()
    assert app._display_badge == ("loading" if phase == "loading" else "engine")
    assert app._handle_ipc("status") == expected


@pytest.mark.parametrize("badge", ["too_short", "pasted", "missed"])
def test_model_reload_after_result_expiry_publishes_loading(model_app, result_timers, monkeypatch, badge):
    app = model_app.app
    app._start_model_warmup()
    model_app.workers[0].run()
    app._flash(badge)
    result_timers[0].fire()
    assert app._display_badge == "hide"
    monkeypatch.setattr("utterleaf.config.load", lambda: replace(app.cfg, model="base"))

    app.reload_config()

    assert app._display_badge == "loading"
    assert app._model_phase == "loading"
    assert app._handle_ipc("status") == "status-v1:processing"


@pytest.mark.parametrize("next_action", ["opening", "listening", "result", "error", "quit"])
def test_old_result_timer_cannot_write_after_new_activity_or_quit(model_app, result_timers, next_action):
    app = model_app.app
    app._flash("too_short")
    old_timer = result_timers[0]
    if next_action == "quit":
        app.quit()
    elif next_action == "result":
        app._flash("pasted", "Newer result")
    else:
        _activity(app, next_action)
    before = _presentation(app)
    calls_before = list(app.indicator.calls)
    generation = app._indicator_generation

    old_timer.fire()

    assert _presentation(app) == before
    assert app.indicator.calls == calls_before
    assert app._indicator_generation == generation


def test_quit_clears_private_caption_and_late_publishers_cannot_restore_it(model_app, result_timers):
    app = model_app.app
    private_caption = "Private dictated text from a confidential document"
    app._flash("pasted", private_caption)
    app._model_caption = DOWNLOADING
    assert app._display_caption == private_caption
    calls_before = list(app.indicator.calls)

    app.quit()

    assert app._display_caption == ""
    assert app._model_caption == ""
    assert app.indicator.calls == calls_before
    presentation_after_quit = _presentation(app)
    generation_after_quit = app._indicator_generation

    result_timers[0].fire()
    app._set_icon("idle", "Late result", badge="pasted", caption=private_caption)

    assert app._display_caption == ""
    assert app._model_caption == ""
    assert _presentation(app) == presentation_after_quit
    assert app.indicator.calls == calls_before
    assert app._indicator_generation == generation_after_quit


@pytest.mark.parametrize("badge", ["no_mic", "capture_error", "transcribe", "no_paste"])
def test_error_expiry_hides_only_overlay_after_model_recovers(model_app, result_timers, badge):
    app = model_app.app
    app._start_model_warmup()
    app._show_error(badge, "Action needs attention", "Retry the operation", seconds=4)
    model_app.workers[0].run()
    assert app._model_phase == "ready"
    before = _presentation(app)
    calls_before = list(app.indicator.calls)

    result_timers[0].fire()

    assert app._handle_ipc("status") == "status-v1:attention"
    assert _presentation(app) == before
    assert app.indicator.calls == calls_before + [("hide", "")]


@pytest.mark.parametrize("phase,expected", [
    ("loading", "status-v1:processing"), ("failed", "status-v1:attention"),
])
def test_idle_status_token_does_not_hide_durable_loading_or_failure(model_app, phase, expected):
    app = model_app.app
    app._reported_status = "status-v1:idle"
    app._model_phase = phase
    assert app._handle_ipc("status") == expected
    assert app._reported_status == "status-v1:idle"


@pytest.mark.parametrize("revoke_at", ["queued", "pick", "probe"])
def test_permission_revoked_before_load_restricts_frozen_request(model_app, monkeypatch, revoke_at):
    app = model_app.app
    app.cfg.allow_network = True
    app._start_model_warmup()
    generation = app._model_generation

    def revoke():
        monkeypatch.setattr("utterleaf.config.load", lambda: replace(app.cfg, allow_network=False))
        app.reload_config()

    def pick(cfg):
        if revoke_at == "pick":
            revoke()
        return model_app.chosen

    def needs_download(chosen, cfg=None):
        if revoke_at == "probe":
            revoke()
        return True

    monkeypatch.setattr(app_module, "pick", pick)
    monkeypatch.setattr(app, "_needs_download", needs_download)
    if revoke_at == "queued":
        revoke()

    model_app.workers[0].run()

    assert app._model_generation == generation
    assert len(model_app.workers) == 1
    loaded_cfg = next(call[1] for call in model_app.calls if call[0] == "load")
    assert loaded_cfg.allow_network is False
    assert loaded_cfg.model == "tiny"
    assert ("loading", DOWNLOADING) not in app.indicator.calls


def test_later_network_opt_in_does_not_upgrade_already_queued_request(model_app, monkeypatch):
    app = model_app.app
    assert not app.cfg.allow_network
    app._start_model_warmup()
    monkeypatch.setattr("utterleaf.config.load", lambda: replace(app.cfg, allow_network=True))
    monkeypatch.setattr(app, "_needs_download", lambda *args: pytest.fail("offline request probed downloads"))

    app.reload_config()
    model_app.workers[0].run()

    assert app.cfg.allow_network
    loaded_cfg = next(call[1] for call in model_app.calls if call[0] == "load")
    assert loaded_cfg.allow_network is False
    assert ("loading", DOWNLOADING) not in app.indicator.calls


@pytest.mark.parametrize("stage", ["pick", "probe"])
@pytest.mark.parametrize("change", ["quit", "new_generation"])
def test_warmup_rechecks_quit_and_generation_after_pick_or_probe(model_app, monkeypatch, stage, change):
    app = model_app.app
    app.cfg.allow_network = True
    app._start_model_warmup()
    generation = app._model_generation

    def supersede():
        if change == "quit":
            app.quit()
        else:
            monkeypatch.setattr("utterleaf.config.load", lambda: replace(app.cfg, model="base"))
            app.reload_config()

    def pick(cfg):
        if stage == "pick":
            supersede()
        return model_app.chosen

    def needs_download(chosen, cfg=None):
        if stage == "probe":
            supersede()
        return True

    monkeypatch.setattr(app_module, "pick", pick)
    monkeypatch.setattr(app, "_needs_download", needs_download)

    model_app.workers[0].run()

    assert model_app.calls == []
    assert app._model_phase == "loading"
    assert ("loading", DOWNLOADING) not in app.indicator.calls
    assert app._model_generation == generation + (change == "new_generation")
    assert len(model_app.workers) == (2 if change == "new_generation" else 1)
