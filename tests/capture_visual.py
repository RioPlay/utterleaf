"""Bounded before/after Settings captures using the guarded baseline fixtures.

No microphone, model download, app connection or preference writes are allowed.
Run with --phase before before editing, then --phase after for the same frames.
"""
import argparse
from pathlib import Path

from capture_settings import _blocked_runtime, _window, _capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('before', 'after'), required=True)
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / 'artifacts/screenshots/visual' / args.phase
    output.mkdir(parents=True, exist_ok=True)
    with _blocked_runtime() as runtime:
        with _window(runtime) as window:
            for page, slug in (('Dictation', 'dictation'), ('Engine', 'speech-privacy')):
                _capture(window, f'{slug}.png', page, output=output)
    print(output)


if __name__ == '__main__':
    main()
