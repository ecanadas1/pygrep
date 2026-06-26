import signal
import sys
from pathlib import Path
from typing import Any
from pygrep_core.constants import ExitCode
from pygrep_core.config import setup_argparse, build_config, GrepArgs
from pygrep_core.output import (
    MatchStats,
    MatchRecord,
    format_filename,
    write_output_file,
    print_stats,
    print_summary,
    print_timeline,
    check_threshold_alerts,
)
from pygrep_core.engine import process_stream, follow_stream
from pygrep_core.discovery import discover_files, process_file

def setup_windows_console() -> None:
    """Habilita el procesamiento de terminal virtual (ANSI) en consolas Windows."""
    import os
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11, STD_ERROR_HANDLE = -12
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        for handle_id in (-11, -12):
            h = kernel32.GetStdHandle(handle_id)
            if h and h != -1:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h, mode.value | 0x0004)

def main() -> None:
    """Punto de entrada principal de la aplicación."""
    setup_windows_console()

    def _signal_handler(signum: int, frame: Any) -> None:
        sys.exit(ExitCode.ERROR)

    if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    if hasattr(signal, "SIGTERM"): signal.signal(signal.SIGTERM, _signal_handler)

    parser = setup_argparse()
    args = parser.parse_args(namespace=GrepArgs())

    has_glob = any(c in f for f in args.files for c in "*?[]")
    has_dir  = any(Path(f).is_dir() for f in args.files if f != "-" and not any(c in f for c in "*?[]"))
    multiple_inputs = len(args.files) > 1 or args.recursive or has_glob or has_dir
    use_stdin = "-" in args.files

    config = build_config(args, multiple_inputs)

    global_match = False
    any_error    = False
    stats        = MatchStats()
    records: list[MatchRecord] = []
    seen: set[str] | None = set() if config.unique else None

    if config.follow:
        follow_files = [Path(f) for f in args.files if f != "-" and Path(f).is_file()]
        if not follow_files:
            print("pygrep: --follow requiere al menos un archivo regular", file=sys.stderr)
            sys.exit(ExitCode.ERROR)

        # Forzar volcado inmediato de stdout (esencial para tiempo real)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)

        print_headers = len(follow_files) > 1
        try:
            for file_path in follow_files:
                if print_headers:
                    print(f"\n==> {file_path} <==\n")
                
                # Calcular el número inicial de línea
                start_line = 1
                try:
                    with open(file_path, "r", encoding=config.encoding, errors="replace") as f:
                        for _ in f:
                            start_line += 1
                except Exception:
                    pass

                live_gen = follow_stream(file_path, config)
                matches, _ = process_stream(live_gen, file_path, config, seen, records, stats, start_line=start_line)
                if matches > 0:
                    global_match = True
                
                if print_headers:
                    print()
        except KeyboardInterrupt:
            pass
        
        # En modo follow no guardamos output ni mostramos resúmenes
        sys.exit(ExitCode.MATCH if global_match else ExitCode.NO_MATCH)

    try:
        if use_stdin:
            match_count, line_count = process_stream(sys.stdin, None, config, seen, records, stats)
            if match_count > 0:
                global_match = True
            if config.show_stats or config.show_summary:
                stats.record_file("<stdin>", match_count, line_count)

        for file_path in discover_files(args.files, config.max_depth, config):
            matched, errored, match_count, line_count = process_file(file_path, config, seen, records, stats)
            if matched:  global_match = True
            if errored:  any_error    = True
            if config.show_stats or config.show_summary:
                stats.record_file(format_filename(file_path), match_count, line_count)

    except KeyboardInterrupt:
        sys.exit(ExitCode.ERROR)

    if config.output_file:
        write_output_file(records, config)

    if config.rate_interval:
        print_timeline(records, config.rate_interval, config.use_color, threshold=config.threshold)

    if config.window_minutes is not None and config.threshold is not None:
        check_threshold_alerts(records, config.window_minutes, config.threshold, config.use_color)

    if config.show_stats:
        print_stats(stats, config)

    if config.show_summary:
        print_summary(stats, config)

    sys.exit(ExitCode.ERROR if any_error else (ExitCode.MATCH if global_match else ExitCode.NO_MATCH))