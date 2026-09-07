import numpy as np

from utterleaf.clean import estimate_snr_db, prepare, should_denoise


def _tone(seconds: float = 1.0, hz: float = 220.0, sr: int = 16000) -> np.ndarray:
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    return (0.4 * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def test_empty_passthrough() -> None:
    out = prepare(np.zeros(0, dtype=np.float32))
    assert out.size == 0


def test_clean_tone_has_high_snr() -> None:
    assert estimate_snr_db(_tone()) > 16
    assert should_denoise(_tone()) is False


def test_auto_keeps_clean_tone_shape() -> None:
    tone = _tone()
    out = prepare(tone, mode="auto")
    # Correlation stays high — we did not wreck the speech-like signal.
    n = min(len(tone), len(out))
    corr = float(np.corrcoef(tone[:n], out[:n])[0, 1])
    assert corr > 0.9


def test_hissy_pauses_trigger_denoise() -> None:
    rng = np.random.default_rng(0)
    sr = 16000
    speech = _tone(0.4)
    pause = rng.normal(0, 0.08, int(0.3 * sr)).astype(np.float32)
    clip = np.concatenate([pause, speech, pause])
    assert should_denoise(clip) is True


def test_peak_is_normalized() -> None:
    quiet = _tone() * 0.05
    out = prepare(quiet, mode="off")
    assert float(np.max(np.abs(out))) > 0.7
