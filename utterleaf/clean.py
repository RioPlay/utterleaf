"""Prepare a take for Whisper. Clean only when noise would actually hurt."""

from __future__ import annotations

import logging

import numpy as np

from utterleaf.audio import SAMPLE_RATE

log = logging.getLogger("utterleaf")

PEAK = 0.85
HIGHPASS_HZ = 80.0
MIN_SECONDS = 0.25


def _frame_energy(audio: np.ndarray, sr: int) -> np.ndarray:
    frame = max(sr // 50, 32)
    n = (len(audio) // frame) * frame
    if n < frame * 4:
        return np.array([], dtype=np.float32)
    frames = audio[:n].reshape(-1, frame)
    return np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)


def _spectral_flatness(audio: np.ndarray, n_fft: int = 512) -> float:
    usable = len(audio) - (len(audio) % n_fft)
    if usable < n_fft * 2:
        return 0.0
    window = np.hanning(n_fft)
    frames = audio[:usable].reshape(-1, n_fft) * window
    power = np.mean(np.abs(np.fft.rfft(frames, axis=1)) ** 2, axis=0) + 1e-12
    return float(np.exp(np.mean(np.log(power))) / np.mean(power))


def estimate_snr_db(audio: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    energy = _frame_energy(audio, sr)
    if energy.size == 0:
        return 99.0
    noise = float(np.percentile(energy, 20))
    speech = float(np.percentile(energy, 85))
    if speech > 2.5 * noise and noise > 1e-8:
        return 20.0 * np.log10(speech / noise)
    # No pause structure (held tone or constant hiss). Tonal = clean; flat = noise.
    if _spectral_flatness(audio) < 0.25:
        return 40.0
    return 6.0


def should_denoise(audio: np.ndarray, sr: int = SAMPLE_RATE) -> bool:
    """True only when quiet parts still look like hiss. Skip clean speech."""
    if len(audio) < int(sr * MIN_SECONDS):
        return False
    energy = _frame_energy(audio, sr)
    if energy.size == 0:
        return False
    peak = float(np.max(np.abs(audio))) + 1e-8
    noise = float(np.percentile(energy, 20))
    speech = float(np.percentile(energy, 85))
    if speech > 2.5 * noise:
        return noise > 0.06 * peak
    return _spectral_flatness(audio) > 0.35


def _highpass(audio: np.ndarray, sr: int, cutoff: float = HIGHPASS_HZ) -> np.ndarray:
    # One-pole high-pass. Removes rumble without a scipy dependency.
    # Vectorized per block via the closed form y_j = a^(j+1)*Y0 + a^j*cumsum(d/a^k);
    # 512-sample blocks keep a^-k small enough that float64 precision holds.
    dt = 1.0 / sr
    rc = 1.0 / (2.0 * np.pi * cutoff)
    alpha = rc / (rc + dt)
    y = np.empty_like(audio)
    y[0] = audio[0]
    prev_y = audio[0]
    BLOCK = 512
    for start in range(1, len(audio), BLOCK):
        end = min(start + BLOCK, len(audio))
        j = np.arange(end - start)
        d = alpha * (audio[start:end] - audio[start - 1 : end - 1])
        block = (alpha ** (j + 1)) * prev_y + (alpha**j) * np.cumsum(d / (alpha**j))
        y[start:end] = block
        prev_y = block[-1]
    if audio.dtype == np.float32:
        return y.astype(np.float32)
    return y


def _peak_norm(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-6:
        return audio
    return np.clip(audio * (PEAK / peak), -1.0, 1.0).astype(np.float32)


def _spectral_gate(audio: np.ndarray, sr: int) -> np.ndarray:
    n_fft = 512
    hop = 128
    if len(audio) < n_fft * 2:
        return audio
    window = np.hanning(n_fft).astype(np.float32)
    pad = (-(len(audio) - n_fft) % hop) % hop
    work = np.pad(audio, (0, pad))
    frames = np.lib.stride_tricks.sliding_window_view(work, n_fft)[::hop]
    spec = np.fft.rfft(frames * window, axis=1)
    mag = np.abs(spec)
    # Quietest frames are the noise floor.
    frame_e = np.mean(mag, axis=1)
    quiet = mag[frame_e <= np.percentile(frame_e, 25)]
    if quiet.size == 0:
        return audio
    noise = np.median(quiet, axis=0)
    # Mild subtract; keep a floor so consonants survive.
    cleaned = np.maximum(mag - 0.55 * noise, 0.25 * mag)
    phase = np.exp(1j * np.angle(spec))
    rebuilt = np.fft.irfft(cleaned * phase, n=n_fft, axis=1) * window
    out = np.zeros(len(work) + n_fft, dtype=np.float32)
    win_sum = np.zeros_like(out)
    for i, frame in enumerate(rebuilt):
        start = i * hop
        out[start : start + n_fft] += frame
        win_sum[start : start + n_fft] += window
    win_sum = np.maximum(win_sum, 1e-6)
    return (out / win_sum)[: len(audio)].astype(np.float32)


def prepare(audio: np.ndarray, *, mode: str = "auto", sr: int = SAMPLE_RATE) -> np.ndarray:
    """Return audio Whisper should hear. `auto` denoises only on low SNR."""
    if audio.size == 0:
        return audio
    work = np.ascontiguousarray(audio, dtype=np.float32)
    work = work - float(np.mean(work))
    if len(work) >= int(sr * 0.05):
        work = _highpass(work, sr)
    mode = (mode or "auto").strip().lower()
    snr = estimate_snr_db(work, sr)
    denoise = False
    if mode == "on":
        denoise = len(work) >= int(sr * MIN_SECONDS)
    elif mode == "auto":
        denoise = should_denoise(work, sr)
    if denoise:
        work = _spectral_gate(work, sr)
        log.info("Audio: light denoise (snr=%.1f dB)", snr)
    else:
        log.info("Audio: normalize only (snr=%.1f dB)", snr)
    return _peak_norm(work)
