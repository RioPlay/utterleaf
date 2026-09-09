"""Manual visual QA: python tests/capture_settings.py (no microphone or writes to user config)."""
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
from utterleaf.config import Config
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

output = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
output.mkdir(parents=True, exist_ok=True)
enable_dpi_awareness()
root = tk.Tk()
with patch("utterleaf.settings_ui.startup_enabled", return_value=False), patch(
    "utterleaf.settings_ui.dictionary_text", return_value="utter leaf = Utterleaf\nacme = Acme"
):
    window = SettingsWindow(root, Config(), background=False)
root.geometry("960x780+80+60")
root.attributes("-topmost", True)
root.update()
time.sleep(0.3)
for name in window.pages:
    window.show_page(name)
    # Layout changes can schedule further resize and repaint events. Pump the
    # event loop through settling instead of capturing an intermediate frame.
    for _ in range(6):
        root.update()
        time.sleep(0.05)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    (ImageGrab.grab(window=root.winfo_id()) if sys.platform == "win32" else ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()))).save(
        output / (name.lower().replace(" & ", "-").replace(" ", "-") + ".png")
    )
root.geometry("760x560+80+60")
window.show_page("Dictation")
root.update()
time.sleep(0.15)
x, y = root.winfo_rootx(), root.winfo_rooty()
(ImageGrab.grab(window=root.winfo_id()) if sys.platform == "win32" else ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()))).save(output / "compact.png")
window.show_appearance()
guide = window.appearance_guide
for tab_name in ("Tray states", "App badges", "Cutout marks", "Utterling", "Wordmark"):
    index = list(guide.canvases).index(tab_name)
    guide.tabs.select(index)
    guide.root.update()
    time.sleep(.2)
    (ImageGrab.grab(window=guide.root.winfo_id()) if sys.platform == "win32" else ImageGrab.grab(bbox=(guide.root.winfo_rootx(), guide.root.winfo_rooty(), guide.root.winfo_rootx()+guide.root.winfo_width(), guide.root.winfo_rooty()+guide.root.winfo_height()))).save(output / ("guide-" + tab_name.lower().replace(" ", "-") + ".png"))
guide.root.destroy()
print(output)
window.close()
