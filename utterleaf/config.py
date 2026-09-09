"""Load and save Utterleaf settings from the user config directory."""

from __future__ import annotations

import os
import json
import sys
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from utterleaf.host import default_hotkey


def data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "Utterleaf"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Utterleaf"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "utterleaf" if xdg else Path.home() / ".config" / "utterleaf"


def config_path() -> Path:
    return data_dir() / "config.toml"


def dictionary_path() -> Path:
    return data_dir() / "dictionary.txt"


def log_path() -> Path:
    return data_dir() / "utterleaf.log"


def models_dir() -> Path:
    return data_dir() / "models"


@dataclass
class Config:
    # Push-to-talk. Empty factory picks a combo that does not fight this OS.
    hotkey: str = field(default_factory=default_hotkey)
    mode: str = "hold"  # hold = push-to-talk | toggle
    # Do not swallow every key. Dedicated-key swallow is a later enhancement.
    suppress_hotkey: bool = False

    # Small on-device model. auto device = NPU, then GPU, then CPU.
    model: str = "small"  # tiny, base, small, medium, large-v3, distil-small.en
    device: str = "auto"  # auto | npu | gpu | cpu
    compute_type: str = "auto"  # auto | int8 | float16 | int8_float16
    language: str = "en"  # ISO code, or "auto"
    # auto = denoise only when the take looks noisy. Whisper prefers raw audio when it's already clean.
    denoise: str = "auto"  # auto | on | off
    # True = may fetch missing weights once. After that the app stays offline.
    allow_network: bool = True
    # Empty = OS default input. A name from Settings / --doctor pins a specific mic.
    microphone: str = ""

    # Local rules only. Unknown keys in an old config.toml (polish, ollama, …) are ignored.
    text_cleanup: bool = True
    remove_fillers: bool = True
    fix_corrections: bool = True

    restore_clipboard: bool = True
    tray: bool = True
    indicator: bool = True
    live_preview: bool = False
    beep: bool = True
    min_seconds: float = 0.35
    max_seconds: float = 120.0


def _parse_toml(text: str) -> dict[str, object]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - py<3.11
        import tomli as tomllib  # type: ignore

    return tomllib.loads(text) if text.strip() else {}


def _dump_toml(cfg: Config) -> str:
    # JSON strings are valid TOML basic strings, including quotes and backslashes.
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    lines = [
        "# Utterleaf settings. Everyday use is Settings; this file reloads when you Save.",
        "# Hand-edits apply the next time Settings saves, or at next launch.",
        "",
        "# hold = push-to-talk. Default hotkey is ctrl+win on Windows, ctrl+shift+space elsewhere.",
        f'hotkey = {quote(cfg.hotkey)}',
        f'mode = {quote(cfg.mode)}',
        f"suppress_hotkey = {str(cfg.suppress_hotkey).lower()}",
        "",
        "# Small local model. device=auto uses NPU, then GPU, then CPU.",
        f'model = {quote(cfg.model)}',
        f'device = {quote(cfg.device)}',
        f'compute_type = {quote(cfg.compute_type)}',
        f'language = {quote(cfg.language)}',
        f'denoise = {quote(cfg.denoise)}',
        f"allow_network = {str(cfg.allow_network).lower()}",
        f'microphone = {quote(cfg.microphone)}',
        "",
        f"text_cleanup = {str(cfg.text_cleanup).lower()}",
        f"remove_fillers = {str(cfg.remove_fillers).lower()}",
        f"fix_corrections = {str(cfg.fix_corrections).lower()}",
        "",
        f"restore_clipboard = {str(cfg.restore_clipboard).lower()}",
        f"tray = {str(cfg.tray).lower()}",
        f"indicator = {str(cfg.indicator).lower()}",
        f"live_preview = {str(cfg.live_preview).lower()}",
        f"beep = {str(cfg.beep).lower()}",
        f"min_seconds = {cfg.min_seconds}",
        f"max_seconds = {cfg.max_seconds}",
        "",
    ]
    return "\n".join(lines)


def load() -> Config:
    path = config_path()
    if not path.exists():
        return Config()
    raw = _parse_toml(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    values = {k: v for k, v in raw.items() if k in known}
    return Config(**values)


def save(cfg: Config) -> Path:
    return atomic_write_text(config_path(), _dump_toml(cfg))


def atomic_write_text(path: Path, text: str) -> Path:
    """A failed write must not truncate the previously saved file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def ensure_files() -> Config:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = config_path()
    if not path.exists():
        save(Config())
    dict_path = dictionary_path()
    if not dict_path.exists():
        dict_path.write_text(
            "# One replacement per line: spoken form = written form\n"
            "# utter leaf = Utterleaf\n",
            encoding="utf-8",
        )
    return load()


def as_public_dict(cfg: Config) -> dict[str, object]:
    return asdict(cfg)
