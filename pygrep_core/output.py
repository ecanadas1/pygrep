import csv
import json
import os
import sys
import time
import io
import re
from pathlib import Path
from dataclasses import dataclass, field

from pygrep_core.constants import (
    ExitCode,
    COLOR_RESET,
    COLOR_MATCH,
    COLOR_FILENAME,
    COLOR_LINENUM,
    COLOR_SEPARATOR,
    COLOR_STATS_HDR,
    COLOR_STATS_VAL,
    ANSI_ESCAPE_RE,
    LOG_LEVEL_RE,
)
from pygrep_core.config import Config
from pygrep_core.parser_utils import parse_timestamp


@dataclass
class MatchStats:
    """Acumula estadísticas globales durante la búsqueda."""
    total_files: int = 0
    files_with_matches: int = 0
    total_lines: int = 0
    total_matches: int = 0
    start_time: float = field(default_factory=time.monotonic)
    file_match_counts: dict[str, int] = field(default_factory=dict)
    log_level_counts: dict[str, int] = field(default_factory=lambda: {
        "ERROR": 0,
        "WARN": 0,
        "INFO": 0,
        "DEBUG": 0,
        "FATAL": 0,
        "CRITICAL": 0,
        "MAJOR": 0,
        "MINOR": 0,
        "CLEAR": 0,
    })

    def record_file(self, path: str, match_count: int, line_count: int) -> None:
        self.total_files += 1
        self.total_lines += line_count
        self.total_matches += match_count
        if match_count > 0:
            self.files_with_matches += 1
            self.file_match_counts[path] = match_count

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time


@dataclass
class MatchRecord:
    """Registro de una coincidencia para exportación a fichero."""
    file: str
    line_num: int | None
    content: str


def format_filename(file_path: Path) -> str:
    """Prepara y formatea la ruta de un archivo para su visualización.
    
    Devuelve la ruta relativa si es descendiente del directorio actual,
    o bien el nombre directamente. Sanitiza el string resultante.
    """
    name = str(file_path) if file_path.parent != Path(".") else file_path.name
    return sanitize_string(name)


def colorize(text: str, code: str) -> str:
    """Aplica secuencias de escape ANSI para colorear una cadena de texto."""
    return f"{code}{text}{COLOR_RESET}"


def colorize_matches(line: str, pattern: re.Pattern[str]) -> str:
    """Colorea las coincidencias en una línea."""
    return pattern.sub(lambda m: f"{COLOR_MATCH}{m.group(0)}{COLOR_RESET}", line)


def handle_broken_pipe() -> None:
    """Maneja el error BrokenPipeError al redirigir la salida (p. ej. a head o less).
    
    Redirige sys.stdout a devnull y finaliza la ejecución de forma limpia.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, sys.stdout.fileno())
        finally:
            os.close(devnull)
    except (OSError, AttributeError, io.UnsupportedOperation):
        pass
    sys.exit(ExitCode.MATCH)


def safe_print(text: str, flush: bool = False) -> None:
    """Imprime texto de forma segura controlando errores de codificación y pipes rotos."""
    try:
        print(text, flush=flush) # ← FORZAR VACIADO CUANDO SE PIDA
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((text + "\n").encode("utf-8"))
            if flush: sys.stdout.buffer.flush()  # ← TAMBÉN EN FALLBACK
        except BrokenPipeError:
            handle_broken_pipe()
    except BrokenPipeError:
        handle_broken_pipe()


def sanitize_string(text: str) -> str:
    """SECURITY: Elimina secuencias ANSI y reemplaza caracteres de control no imprimibles."""
    text = ANSI_ESCAPE_RE.sub("", text)
    return "".join(c if c.isprintable() or c == "\t" else "?" for c in text)


def format_and_print_event(event, file_path: Path | None, config: Config) -> None:
    """Formatea e imprime un evento de salida de coincidencia o contexto.
    
    Aplica colores ANSI si el coloreado está habilitado en `config`, muestra el
    nombre del archivo y número de línea según proceda, y resalta las partes coincidentes.
    """
    # event is engine.OutputEvent
    if event.is_match is None:
        safe_print(colorize("--", COLOR_SEPARATOR) if config.use_color else "--")
        return

    parts: list[str] = []
    sep_char = ":" if event.is_match else "-"

    if config.show_filename and file_path is not None:
        fname = format_filename(file_path)
        parts.append((colorize(fname, COLOR_FILENAME) + sep_char) if config.use_color else f"{fname}{sep_char}")

    if config.line_number and event.line_num is not None:
        ln_str = str(event.line_num)
        parts.append((colorize(ln_str, COLOR_LINENUM) + sep_char) if config.use_color else f"{ln_str}{sep_char}")

    content = sanitize_string(event.content)
    if config.use_color and event.is_match:
        if event.match_span is not None:
            start, end = event.match_span
            if start < end:
                before = content[:start]
                matched = content[start:end]
                after = content[end:]
                content = before + COLOR_MATCH + matched + COLOR_RESET + after
        else:
            content = colorize_matches(content, config.pattern)
    parts.append(content)

    safe_print("".join(parts), flush=config.follow)


def print_stats(stats: MatchStats, config: Config) -> None:
    """Imprime el resumen de estadísticas en stderr al finalizar."""
    use_color = config.use_color
    sep = "-" * 54
    title = "[ Estadisticas de busqueda ]"

    def h(text: str) -> str:
        return colorize(text, COLOR_STATS_HDR) if use_color else text

    def v(val: str) -> str:
        return colorize(val, COLOR_STATS_VAL) if use_color else val

    rate = (stats.total_matches / stats.total_lines * 100) if stats.total_lines > 0 else 0.0

    print(file=sys.stderr)
    print(h(f"{title:^54}"), file=sys.stderr)
    print(h(sep), file=sys.stderr)
    print(f"  Archivos analizados    : {v(f'{stats.total_files:,}')}", file=sys.stderr)
    print(f"  Archivos con matches   : {v(f'{stats.files_with_matches:,}')}", file=sys.stderr)
    print(f"  Lineas procesadas      : {v(f'{stats.total_lines:,}')}", file=sys.stderr)
    print(f"  Coincidencias totales  : {v(f'{stats.total_matches:,}')}", file=sys.stderr)
    print(f"  Tasa de coincidencia   : {v(f'{rate:.2f}%')}", file=sys.stderr)
    print(f"  Tiempo transcurrido    : {v(f'{stats.elapsed:.3f}s')}", file=sys.stderr)

    if stats.file_match_counts:
        top = sorted(stats.file_match_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        print(h("\n  Top archivos con mas coincidencias:"), file=sys.stderr)
        for fname, count in top:
            display = fname if len(fname) <= 40 else "..." + fname[-37:]
            print(f"    {display:<42} {v(str(count)):>6}", file=sys.stderr)

    print(h(sep), file=sys.stderr)


def print_summary(stats: MatchStats, config: Config) -> None:
    """Imprime un resumen de nivel de log en formato tabla."""
    total = sum(stats.log_level_counts.values())
    
    safe_print("Nivel    │ Ocurrencias │ Porcentaje")
    safe_print("─────────┼─────────────┼───────────")
    
    levels_to_print = ["ERROR", "WARN", "INFO", "DEBUG"]
    if stats.log_level_counts.get("FATAL", 0) > 0:
        levels_to_print.append("FATAL")
    if stats.log_level_counts.get("CRITICAL", 0) > 0:
        levels_to_print.append("CRITICAL")
    if stats.log_level_counts.get("MAJOR", 0) > 0:
        levels_to_print.append("MAJOR")
    if stats.log_level_counts.get("MINOR", 0) > 0:
        levels_to_print.append("MINOR")
    if stats.log_level_counts.get("CLEAR", 0) > 0:
        levels_to_print.append("CLEAR")
        
    for lvl in levels_to_print:
        count = stats.log_level_counts.get(lvl, 0)
        pct = (count / total * 100) if total > 0 else 0.0
        
        lvl_str = f"{lvl:<8}"
        count_str = f"{count:,}"
        count_padded = f"{count_str:<11}"
        pct_padded = f"{pct:>5.1f}%"
        
        safe_print(f"{lvl_str} │ {count_padded} │ {pct_padded}")


def write_output_file(records: list[MatchRecord], config: Config) -> None:
    """Escribe los resultados en el fichero de salida con el formato elegido."""
    if not config.output_file:
        return
    try:
        out_path = Path(config.output_file)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            if config.output_format == "json":
                data = [
                    {"file": r.file if config.show_filename else None, "line": r.line_num, "content": r.content}
                    for r in records
                ]
                json.dump(data, f, ensure_ascii=False, indent=2)
            elif config.output_format == "csv":
                writer = csv.writer(f)
                writer.writerow(["file", "line", "content"])
                for r in records:
                    writer.writerow([r.file if config.show_filename else "", r.line_num if r.line_num is not None else "", r.content])
            else:  # text
                for r in records:
                    parts: list[str] = []
                    if r.file and config.show_filename:
                        parts.append(r.file)
                    if r.line_num is not None:
                        parts.append(str(r.line_num))
                    parts.append(r.content)
                    f.write(":".join(parts) + "\n")

        print(
            f"pygrep: {len(records)} resultado(s) escritos en '{config.output_file}' "
            f"(formato: {config.output_format})",
            file=sys.stderr,
        )
    except OSError as e:
        print(f"pygrep: error al escribir '{config.output_file}': {e}", file=sys.stderr)


def check_threshold_alerts(
    records: list["MatchRecord"],
    window_minutes: int,
    threshold: int,
    use_color: bool,
) -> int:
    """Detecta ventanas temporales donde las coincidencias superan el umbral dado.

    Utiliza una ventana deslizante de `window_minutes` minutos sobre los timestamps
    de las coincidencias.  Por cada ventana que supere `threshold` eventos emite
    una alerta en stderr.

    Returns:
        El número de ventanas que superaron el umbral (0 si no hay alertas).
    """
    import datetime
    from collections import deque

    COLOR_WARN  = "\033[01;31m"   # rojo negrita
    COLOR_RESET = "\033[0m"

    # 1. Extraer y ordenar timestamps de los records
    timestamps: list[datetime.datetime] = []
    for r in records:
        dt = parse_timestamp(r.content)
        if dt is not None:
            timestamps.append(dt)

    if not timestamps:
        return 0

    timestamps.sort()
    window_delta = datetime.timedelta(minutes=window_minutes)

    # 2. Ventana deslizante con deque
    window: deque[datetime.datetime] = deque()
    alert_count = 0
    alerted_windows: set[datetime.datetime] = set()  # evitar alertas duplicadas

    print(file=sys.stderr)
    sep = "-" * 66
    title = f" [ Alertas de umbral: >{threshold} eventos en {window_minutes} min ] "
    if use_color:
        print(f"{COLOR_WARN}{title:^66}{COLOR_RESET}", file=sys.stderr)
        print(f"{COLOR_WARN}{sep}{COLOR_RESET}", file=sys.stderr)
    else:
        print(f"{title:^66}", file=sys.stderr)
        print(sep, file=sys.stderr)

    for ts in timestamps:
        window.append(ts)
        # Eliminar eventos fuera de la ventana
        while window and (ts - window[0]) > window_delta:
            window.popleft()

        if len(window) > threshold:
            # La ventana arranca en window[0]; usamos esa como clave de dedup
            window_start = window[0]
            if window_start not in alerted_windows:
                alerted_windows.add(window_start)
                alert_count += 1
                t_ini = window_start.strftime("%Y-%m-%d %H:%M:%S")
                t_fin = ts.strftime("%Y-%m-%d %H:%M:%S")
                msg = (f"  ⚠  ALERTA  [{t_ini} → {t_fin}]  "
                       f"{len(window)} eventos (umbral: {threshold})")
                if use_color:
                    print(f"{COLOR_WARN}{msg}{COLOR_RESET}", file=sys.stderr)
                else:
                    print(msg, file=sys.stderr)

    if alert_count == 0:
        msg = f"  ✓  Sin picos. Todos los intervalos están por debajo del umbral ({threshold})."
        if use_color:
            print(f"\033[32m{msg}\033[0m", file=sys.stderr)
        else:
            print(msg, file=sys.stderr)

    if use_color:
        print(f"{COLOR_WARN}{sep}{COLOR_RESET}", file=sys.stderr)
    else:
        print(sep, file=sys.stderr)
    print(file=sys.stderr)

    return alert_count


def print_timeline(
    records: list["MatchRecord"],
    interval_str: str,
    use_color: bool,
    threshold: int | None = None,
) -> None:
    """Calcula y muestra un histograma de barras ASCII ordenado temporalmente.

    Agrupa los timestamps de records basándose en el intervalo dado (ej: 10s, 1m, 1h).
    Si se pasa `threshold`, las barras que lo superan se marcan con ⚠.
    """
    import datetime

    # 1. Parsear el intervalo (ej: '10s' -> timedelta(seconds=10))
    val = interval_str.strip().lower()
    m = re.match(r'^(\d+)([smh])$', val)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
    else:
        num = 1
        unit = val

    if unit == 's':
        time_fmt = "%Y-%m-%d %H:%M:%S"
    elif unit == 'm':
        time_fmt = "%Y-%m-%d %H:%M"
    else:  # 'h'
        time_fmt = "%Y-%m-%d %H:%M"

    # 2. Extraer y agrupar timestamps
    buckets: dict[datetime.datetime, int] = {}
    for r in records:
        dt = parse_timestamp(r.content)
        if dt is None:
            continue

        if unit == 's':
            seconds = ((dt.hour * 3600 + dt.minute * 60 + dt.second) // num) * num
            base_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(seconds=seconds)
        elif unit == 'm':
            minutes = ((dt.hour * 60 + dt.minute) // num) * num
            base_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(minutes=minutes)
        else:  # 'h'
            hours = (dt.hour // num) * num
            base_dt = dt.replace(hour=hours, minute=0, second=0, microsecond=0)

        buckets[base_dt] = buckets.get(base_dt, 0) + 1

    if not buckets:
        print("pygrep: no se encontraron timestamps válidos para generar la línea temporal.", file=sys.stderr)
        return

    # 3. Ordenar buckets cronológicamente
    sorted_keys = sorted(buckets.keys())
    max_val = max(buckets.values())

    # 4. Renderizar el histograma
    max_bar_width = 40
    print(file=sys.stderr)
    title = f" [ Histograma Temporal ({interval_str}) ] "
    sep = "-" * 60
    if use_color:
        print(f"\033[01;36m{title:^60}\033[0m", file=sys.stderr)
        print(f"\033[36m{sep}\033[0m", file=sys.stderr)
    else:
        print(f"{title:^60}", file=sys.stderr)
        print(sep, file=sys.stderr)

    for k in sorted_keys:
        count = buckets[k]
        bar_len = int((count / max_val) * max_bar_width) if max_val > 0 else 0
        bar = "█" * bar_len + "░" * (max_bar_width - bar_len)
        k_str = k.strftime(time_fmt)
        exceeded = threshold is not None and count > threshold
        marker = " ⚠" if exceeded else "  "

        if use_color:
            bar_color = "\033[01;31m" if exceeded else "\033[32m"
            count_color = "\033[01;31m" if exceeded else "\033[01;33m"
            print(
                f"  {k_str} │ {bar_color}{bar}\033[0m │ "
                f"{count_color}{count:<6}\033[0m{marker}",
                file=sys.stderr,
            )
        else:
            print(f"  {k_str} │ {bar} │ {count:<6}{marker}", file=sys.stderr)

    if use_color:
        print(f"\033[36m{sep}\033[0m", file=sys.stderr)
    else:
        print(sep, file=sys.stderr)
    print(file=sys.stderr)

