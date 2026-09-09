"""Compare local CPU/GPU inference using an existing 16 kHz mono PCM WAV.

Run from the repository root: python scripts/benchmark_dictation.py sample.wav
No downloads, microphone access, or transcript output. Synthetic speech is a
latency smoke check, not an accuracy benchmark for human dictation.
"""
import argparse
import json
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from utterleaf.config import Config
from utterleaf.hardware import Accelerator, pick
from utterleaf.transcribe import _load_ctranslate, reset_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()
    with wave.open(str(args.wav)) as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            parser.error("Expected mono, 16-bit PCM, 16 kHz WAV")
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
    for device in ("cpu", "gpu"):
        cfg = Config(model=args.model, device=device, allow_network=False)
        accel = Accelerator("cpu", "CPU", "ctranslate2", True) if device == "cpu" else pick(cfg)
        if device == "gpu" and (accel.kind != "gpu" or accel.backend != "ctranslate2"):
            print(json.dumps({"requested": device, "skipped": "CUDA unavailable"}), flush=True)
            continue
        started = time.perf_counter()
        engine = _load_ctranslate(cfg, accel)  # Do not hide a failed GPU behind CPU fallback.
        load = time.perf_counter() - started
        durations = []
        for _ in range(3):
            started = time.perf_counter()
            result = engine.transcribe(audio, cfg)
            durations.append(round(time.perf_counter() - started, 3))
            if not result:
                raise RuntimeError("Sample produced no transcription")
        print(json.dumps({"device": device, "model": args.model,
                          "audio_seconds": round(len(audio) / 16000, 3),
                          "load_seconds": round(load, 3),
                          "decode_seconds": durations}), flush=True)
        del engine
        reset_engine()


if __name__ == "__main__":
    main()
