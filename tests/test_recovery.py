from utterleaf.recovery import RecentDictation


class Timer:
    def __init__(self, seconds, callback, args):
        self.callback, self.args = callback, args
        self.cancelled = False
    def start(self):
        pass
    def cancel(self):
        self.cancelled = True
    def fire(self):
        self.callback(*self.args)


def test_latest_only_and_stale_expiry_cannot_delete_new_text():
    recent = RecentDictation(clock=lambda: 0, timer_factory=Timer)
    recent.put("first")
    old_timer = recent._timer
    recent.put("second")
    old_timer.fire()
    assert old_timer.cancelled
    assert recent.get() == "second"
    recent._timer.fire()
    assert recent.get() == ""


def test_deadline_is_enforced_even_if_timer_delivery_is_late():
    now = [10.0]
    recent = RecentDictation(clock=lambda: now[0], timer_factory=Timer)
    recent.put("private text")
    now[0] = 129.9
    assert recent.get() == "private text"
    now[0] = 130
    assert recent.get() == ""
    assert recent._text == ""


def test_forget_cancels_expiry_and_drops_reference():
    recent = RecentDictation(timer_factory=Timer)
    recent.put("private text")
    timer = recent._timer
    recent.clear()
    assert timer.cancelled
    assert recent.get() == ""
    assert recent._timer is None
