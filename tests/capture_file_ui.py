"""Capture file workflow layouts using invented metadata, without media or models."""

import argparse
from fractions import Fraction
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import ImageGrab
from utterleaf.config import Config
from utterleaf.file_decoder_ui import DecoderDialog
from utterleaf.file_inspection import InspectedFile
from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.file_ui import FileWindow
from utterleaf.settings_ui import enable_dpi_awareness
from utterleaf.transcript import Segment, Transcript


def _save(root, output, name, geometry):
    root.geometry(geometry + "+80+60")
    root.deiconify()
    root.lift()
    for _ in range(6):
        root.update()
        time.sleep(.05)
    width, height = map(int, geometry.split("x"))
    if (root.winfo_width(), root.winfo_height()) != (width, height):
        raise RuntimeError(f"{name}: unexpected window dimensions")
    if sys.platform == "win32":
        image = ImageGrab.grab(window=root.winfo_id())
    else:
        x, y = root.winfo_rootx(), root.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    if image.size != (width, height) or not any(a != b for a, b in image.convert("RGB").getextrema()):
        raise RuntimeError(f"{name}: blank or incorrectly sized capture")
    image.save(output / f"{name}.png")


def capture(output):
    output.mkdir(parents=True, exist_ok=True)
    enable_dpi_awareness()
    root = tk.Tk()
    window = FileWindow(root, Config())
    try:
        _save(root, output, "file-empty", "800x640")
        tracks = tuple(MediaAudioTrack(
            ordinal=i, stream_index=i + 1, codec="aac", sample_rate=48000,
            channels=2 if i == 0 else 1, layout="stereo" if i == 0 else "mono",
            title=title, language="eng", is_default=i == 0,
            start=Fraction(i, 2), time_base=Fraction(1, 48000),
        ) for i, title in enumerate(("Complete stream mix", "Host microphone", "Guests and desktop audio")))
        window.path = Path("Community conversation — episode 12.mkv")
        window.filename.set(window.path.name)
        inspected = InspectedFile(MediaMetadata(Fraction(0), "container", tracks), (1, 2, 3))
        window.events.put_nowait(("inspection", inspected))
        root.after_cancel(window.poll_id)
        window.poll()
        window.result = Transcript((Segment(0, 5, "Welcome back. Today we’re looking at the ideas shared by our community."),))
        window._preview(window.result.text)
        window.status.set("Review the transcript, then choose an export format.")
        window._controls()
        _save(root, output, "file-ready", "800x640")
        _save(root, output, "file-compact", "760x560")
        for selected in (False, True):
            prefix = "C:/Applications/Local media tools/Verified release essentials/bin/"
            with patch("utterleaf.file_decoder_ui.decoder_selection", return_value={"path": prefix + "ffmpeg.exe"} if selected else None), patch(
                "utterleaf.file_decoder_ui.probe_selection", return_value={"path": prefix + "ffprobe.exe"} if selected else None
            ):
                dialog = DecoderDialog(root)
            try:
                name = "formats-selected" if selected else "formats-empty"
                _save(dialog.root, output, name, "680x560")
                _save(dialog.root, output, name + "-compact", "560x500")
            finally:
                dialog.root.destroy()
    finally:
        window.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/screenshots/files")
    print(capture(parser.parse_args().output))
