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
    parser.add_argument("--copy-last", action="store_true", help="Copy the latest dictation while its two-minute recovery slot is available")
    parser.add_argument("--forget-last", action="store_true", help="Clear recent dictation and edit context from memory")
    parser.add_argument("--stop", action="store_true", help="Stop a running instance")
    parser.add_argument("--quit", action="store_true", dest="quit_app", help="Quit a running instance")
    parser.add_argument("--polish", metavar="TEXT", help="Polish text on stdout (no mic)")
    parser.add_argument("--app", default="", help="Foreground app name for --polish")
    parser.add_argument("--transcribe-file", metavar="PATH", help="Transcribe a local media file using already installed models")
    parser.add_argument("--files", action="store_true", help="Open local file transcription and export")
    parser.add_argument("--model-setup-download", metavar="NAME", help=argparse.SUPPRESS)
    parser.add_argument("--model-setup-backend", choices=("ctranslate2", "openvino"), help=argparse.SUPPRESS)
    parser.add_argument("--output", metavar="PATH", help="Explicit destination for file transcription")
    parser.add_argument("--format", choices=("txt", "srt", "vtt"), help="Output format (otherwise inferred from destination suffix)")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing the explicitly selected output file")
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

    if args.model_setup_download:
        allowed = {"model_setup_download", "model_setup_backend"}
        if any(value not in (None, False, "") for key, value in vars(args).items() if key not in allowed):
            parser.error("Model setup cannot be combined with another action")
        if not args.model_setup_backend:
            parser.error("Model setup requires an explicit backend")
        from utterleaf.model_setup import download_selected
        return download_selected(args.model_setup_download, args.model_setup_backend)
    if args.model_setup_backend:
        parser.error("A model setup backend requires a selected model")

    if args.transcribe_file:
        if not args.output:
            parser.error("--transcribe-file requires --output; transcripts are not printed or saved implicitly")
        if any((args.files, args.pill, args.settings, args.paths, args.toggle, args.stop, args.quit_app,
                args.copy_last, args.forget_last, args.download_model, args.doctor, args.cuda_setup,
                args.install_startup, args.uninstall_startup, args.polish is not None, args.no_tray, args.app)):
            parser.error("--transcribe-file cannot be combined with another app action")
        from pathlib import Path
        source, destination = Path(args.transcribe_file).expanduser(), Path(args.output).expanduser()
        if not source.is_file():
            parser.error("The selected input file does not exist or is not a file")
        if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
            parser.error("The output must not replace the source media file")
        if destination.exists() and not args.overwrite:
            parser.error("Output already exists; choose another destination or explicitly use --overwrite")
        if args.format is None and destination.suffix.lower() not in (".txt", ".srt", ".vtt"):
            parser.error("Use a .txt, .srt or .vtt output filename, or specify --format")
    elif args.output or args.format or args.overwrite:
        parser.error("--output, --format and --overwrite require --transcribe-file")

    if args.files:
        if any((args.pill, args.settings, args.paths, args.toggle, args.stop, args.quit_app,
                args.copy_last, args.forget_last, args.download_model, args.doctor, args.cuda_setup,
                args.install_startup, args.uninstall_startup, args.polish is not None, args.no_tray, args.app)):
            parser.error("--files cannot be combined with another app action")
        from utterleaf.file_ui import run_files

        return run_files()

    if args.pill:
        from utterleaf.indicator import run_pill

        return run_pill()

    if args.toggle or args.stop or args.quit_app or args.copy_last or args.forget_last:
        from utterleaf import ipc

        command = ("copy-last" if args.copy_last else "forget-last" if args.forget_last
                   else "toggle" if args.toggle else "stop" if args.stop else "quit")
        reply = ipc.send(command)
        if reply is None:
            print("Utterleaf is not running.", file=sys.stderr)
            return 1
        if reply == "restart-required":
            print("Quit the older Utterleaf instance and reopen the updated app before using this command.", file=sys.stderr)
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

    if args.transcribe_file:
        import threading
        from utterleaf.file_transcription import transcribe_file
        from utterleaf.transcript import export_transcript

        cancelled = threading.Event()
        try:
            result = transcribe_file(source, cfg, cancel=cancelled)
            written = export_transcript(result, destination, format=args.format, overwrite=args.overwrite)
        except KeyboardInterrupt:
            cancelled.set()
            print("File transcription cancelled. No new output was requested after cancellation.", file=sys.stderr)
            return 130
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"File transcription failed: {exc}", file=sys.stderr)
            return 1
        print(f"Saved transcription to {written}")
        return 0

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
