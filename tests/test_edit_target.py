from dataclasses import replace

import pytest

from utterleaf import edit_target as edit


def receipt():
    before = edit.Field((1, 2, 3), "Hello ", 6, 6)
    after = edit.Field((1, 2, 3), "Hello world", 11, 11)
    return edit.Receipt(before, after)


@pytest.mark.parametrize("current", [
    None,
    edit.Field((1, 9, 3), "Hello world", 11, 11),  # another field, same window
    edit.Field((1, 2, 8), "Hello world", 11, 11),  # recycled handle
    edit.Field((1, 2, 3), "Hello world!", 12, 12),  # manual typing
    edit.Field((1, 2, 3), "Hello world", 2, 2),  # caret moved
])
def test_changed_or_unknown_field_never_mutates(monkeypatch, current):
    monkeypatch.setattr(edit, "read_field", lambda: current)
    monkeypatch.setattr(edit, "_native_api", lambda: pytest.fail("Must not send an edit"))
    assert edit.replace(receipt(), "everyone") == ("unavailable", None)


def test_capture_requires_exact_insertion_and_handles_utf16(monkeypatch):
    before = edit.Field((1, 2, 3), "🍃 go", 3, 5)
    after = edit.Field((1, 2, 3), "🍃 grow", 7, 7)
    monkeypatch.setattr(edit, "read_field", lambda: after)
    assert edit.capture(before, "grow") == edit.Receipt(before, after)
    monkeypatch.setattr(edit, "read_field", lambda: replace(after, text="🍃 grow!"))
    assert edit.capture(before, "grow") is None


def test_scoped_replacement_uses_selection_and_verifies_result(monkeypatch):
    saved = receipt()
    current = iter([saved.after, edit.Field((1, 2, 3), "Hello world", 6, 11),
                    edit.Field((1, 2, 3), "Hello everyone", 14, 14)])
    monkeypatch.setattr(edit, "read_field", lambda: next(current))
    monkeypatch.setattr(edit, "_native_api", lambda: object())
    calls = []
    monkeypatch.setattr(edit, "_send", lambda api, hwnd, message, *args: calls.append((hwnd, message)))
    outcome, updated = edit.replace(saved, "everyone")
    assert outcome == "replaced"
    assert updated.before == saved.before
    assert updated.after.text == "Hello everyone"
    assert calls == [(2, 0xB1), (2, 0xC2)]


def test_selection_changed_before_replacement_does_not_send_text(monkeypatch):
    saved = receipt()
    current = iter([saved.after, replace(saved.after, start=0, end=5)])
    monkeypatch.setattr(edit, "read_field", lambda: next(current))
    monkeypatch.setattr(edit, "_native_api", lambda: object())
    calls = []
    monkeypatch.setattr(edit, "_send", lambda api, hwnd, message, *args: calls.append(message))
    assert edit.replace(saved, "everyone") == ("failed", None)
    assert calls == [0xB1]


def test_scratch_restores_only_the_originally_replaced_selection(monkeypatch):
    before = edit.Field((1, 2, 3), "Hello old text!", 6, 14)
    after = edit.Field((1, 2, 3), "Hello world", 11, 11)
    current = iter([after, replace(after, start=6), edit.Field((1, 2, 3), before.text, 14, 14)])
    monkeypatch.setattr(edit, "read_field", lambda: next(current))
    monkeypatch.setattr(edit, "_native_api", lambda: object())
    monkeypatch.setattr(edit, "_send", lambda *args: 0)
    assert edit.replace(edit.Receipt(before, after), None)[0] == "replaced"


def test_native_windows_edit_roundtrip_in_hidden_test_control(monkeypatch):
    import sys
    if sys.platform != "win32":
        pytest.skip("Native Windows Edit control")
    import ctypes as c
    from ctypes import wintypes as w
    from types import SimpleNamespace

    native = edit._native_api()
    native.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                       c.c_int, c.c_int, c.c_int, c.c_int,
                                       w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
    native.CreateWindowExW.restype = w.HWND
    native.DestroyWindow.argtypes = [w.HWND]
    hwnd = native.CreateWindowExW(0, "Edit", "Hello old", 4, 0, 0, 200, 100, None, None, None, None)
    assert hwnd
    try:
        # Only substitute focus discovery. All edit messages go to our own
        # hidden native control; no user's window or clipboard is touched.
        def focus(thread, pointer):
            pointer._obj.active = hwnd
            pointer._obj.focus = hwnd
            return 1
        proxy = SimpleNamespace(GetGUIThreadInfo=focus, **{
            name: getattr(native, name) for name in (
                "GetClassNameW", "GetWindowLongW", "IsWindowUnicode", "IsWindowEnabled",
                "GetWindowThreadProcessId", "SendMessageTimeoutW")
        })
        monkeypatch.setattr(edit, "_native_api", lambda: proxy)
        edit._send(native, hwnd, 0xB1, 6, 9)
        before = edit.read_field()
        assert before is not None
        buffer = c.create_unicode_buffer("world")
        edit._send(native, hwnd, 0xC2, 1, c.addressof(buffer))
        saved = edit.capture(before, "world")
        assert saved is not None
        outcome, updated = edit.replace(saved, "everyone 🍃")
        assert outcome == "replaced"
        assert edit.read_field().text == "Hello everyone 🍃"
        assert edit.replace(updated, None)[0] == "replaced"
        assert edit.read_field().text == "Hello old"
    finally:
        native.DestroyWindow(hwnd)
