"""CLI: python -m utterleaf"""

from __future__ import annotations

import argparse
import sys

from utterleaf.offline import apply_offline_defaults

apply_offline_defaults()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="utterleaf",
        description="Hold a hotkey, speak, paste clean text. Local. Windows, macOS, and Linux.",
    )
    parser.add_argument("--doctor", action="store_true", help="Check mic, hotkey, paste helper, and paths")
    parser.add_argument("--cuda-setup", action="store_true", help="Print how to enable the NVIDIA GPU for this build")
    parser.add_argument("--toggle", action="store_true", help="Toggle recording on a running instance")
    parser.add_argument("--stop", action="store_true", help="Stop a running instance")
    parser.add_argument("--quit", action="store_true", dest="quit_app", help="Quit a running instance")
    parser.add_argument("--polish", metavar="TEXT", help="Polish text on stdout (no mic)")
    parser.add_argument("--app", default="", help="Foreground app name for --polish")
    parser.add_argument("--no-tray", action="store_true", help="Run without a tray icon")
    parser.add_argument("--paths", action="store_true", help="Print config paths and exit")
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Fetch missing model weights into the app folder, then exit",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not download anything; fail if weights are missing",
    )
    parser.add_argument(
        "--install-startup",
        action="store_true",
        help="Start Utterleaf at login (silent)",
    )
    parser.add_argument(
        "--uninstall-startup",
        action="store_true",
        help="Remove the login start",
    )
    parser.add_argument("--settings", action="store_true", help="Open the settings window")
    parser.add_argument(
        "--pill",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.pill:
        from utterleaf.indicator import run_pill

        return run_pill()

    if args.toggle or args.stop or args.quit_app:
        from utterleaf import ipc

        command = "toggle" if args.toggle else "stop" if args.stop else "quit"
        reply = ipc.send(command)
        if reply is None:
            print("Utterleaf is not running.", file=sys.stderr)
            return 1
        print(reply)
        return 0 if reply == "ok" else 1

    from utterleaf.config import config_path, data_dir, dictionary_path, ensure_files, log_path

    if args.settings:
        ensure_files()
        from utterleaf.settings import run_settings

        return run_settings()

    if args.paths:
        print(data_dir())
        print(config_path())
        print(dictionary_path())
        print(log_path())
        return 0

    if args.install_startup:
        from utterleaf.startup import install

        print(install())
        return 0

    if args.uninstall_startup:
        from utterleaf.startup import uninstall

        print("removed" if uninstall() else "not installed")
        return 0

    first_run = not config_path().exists()
    cfg = ensure_files()
    if args.no_tray:
        cfg.tray = False
    if args.offline:
        cfg.allow_network = False

    from utterleaf.hardware import enable_cuda_libs

    enable_cuda_libs()

    from utterleaf.app import Utterleaf, run_doctor, run_once, setup_logging

    if args.download_model:
        from utterleaf.transcribe import download_weights

        for path in download_weights(cfg):
            print(path)
        return 0

    if args.doctor:
        return run_doctor(cfg)

    if args.cuda_setup:
        from utterleaf.hardware import cuda_setup_plan

        print("\n".join(cuda_setup_plan()))
        return 0

    if args.polish is not None:
        print(run_once(args.polish, cfg, app_name=args.app))
        return 0

    setup_logging()
    Utterleaf(cfg).run(first_run=first_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
