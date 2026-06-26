import argparse
import codecs
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pygrep_core.constants import (
    ExitCode,
    MAX_CONTEXT_LINES,
    MAX_PATTERN_FILE_SIZE,
    MAX_PATTERN_LINES,
)
from pygrep_core.parser_utils import detect_redos, parse_datetime_arg, parse_kv_filter, parse_json_filter

class GrepArgs(argparse.Namespace):
    pattern: str | None
    file: str | None
    files: list[str]
    ignore_case: bool
    smart_case: bool
    invert_match: bool
    count: bool
    line_number: bool
    recursive: bool
    word_regexp: bool
    fixed_strings: bool
    extended_regexp: bool
    color: str
    encoding: str
    redos_strict: bool
    max_count: int | None
    after_context: int | None
    before_context: int | None
    context: int | None
    files_with_matches: bool
    files_without_matches: bool
    no_filename: bool
    with_filename: bool
    stats: bool
    unique: bool
    include: list[str]
    exclude: list[str]
    ignore_dir: list[str]
    output: str | None
    output_format: str
    search_zip: bool
    extract: bool
    summary: bool
    multiline: bool
    tail: int | None
    time_range: list[str] | None
    auto_encoding: bool
    follow: bool
    kv_mode: bool
    kv_filter: str | None
    kv_skip_non_kv: bool
    json_mode: bool
    json_filter: str | None
    json_skip_non_json: bool
    rate_interval: str | None
    window_minutes: int | None
    threshold: int | None


@dataclass(frozen=True)
class Config:
    pattern: re.Pattern[str]
    pattern_bytes: re.Pattern[bytes] | None  # mmap: búsqueda directa en bytes para --multiline
    smart_case: bool
    invert_match: bool
    count_only: bool
    line_number: bool
    max_depth: int | None
    use_color: bool
    show_filename: bool
    before_context: int
    after_context: int
    max_count: int | None
    files_with_matches: bool
    files_without_matches: bool
    encoding: str
    show_stats: bool
    unique: bool
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    ignore_dirs: tuple[str, ...]
    output_file: str | None
    output_format: str  # "text" | "json" | "csv"
    search_zip: bool
    extract: bool
    show_summary: bool
    multiline: bool
    tail: int | None
    time_range: tuple[datetime.datetime, datetime.datetime] | None
    auto_encoding: bool
    follow: bool
    kv_mode: bool
    kv_filter: tuple[tuple[str, re.Pattern[str]], ...] | None
    kv_skip_non_kv: bool
    json_mode: bool
    json_filter: tuple[tuple[str, re.Pattern[str]], ...] | None
    json_skip_non_json: bool
    rate_interval: str | None
    window_minutes: int | None
    threshold: int | None


def build_pattern(args: GrepArgs) -> re.Pattern[str]:
    """Construye y compila el patrón de expresión regular a partir de los argumentos.
    
    Combina patrones posicionales y patrones leídos desde archivos (-f), aplicando
    opciones como escape de cadenas literales (-F) y coincidencia de palabras
    completas (-w). También analiza el riesgo de ReDoS.
    """
    raw_patterns: list[str] = []
    if args.pattern is not None:
        raw_patterns.append(args.pattern)

    if args.file is not None:
        fpath = Path(args.file)
        try:
            if fpath.stat().st_size > MAX_PATTERN_FILE_SIZE:
                print(f"pygrep: {args.file}: archivo de patrones demasiado grande (>10MB)", file=sys.stderr)
                sys.exit(ExitCode.ERROR)
        except OSError:
            pass

        try:
            with fpath.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= MAX_PATTERN_LINES:
                        print(f"pygrep: {args.file}: demasiados patrones (>{MAX_PATTERN_LINES})", file=sys.stderr)
                        sys.exit(ExitCode.ERROR)
                    raw_patterns.append(line.rstrip("\r\n"))
        except OSError as e:
            print(f"pygrep: {args.file}: {e}", file=sys.stderr)
            sys.exit(ExitCode.ERROR)

    if not raw_patterns:
        print("pygrep: no se especificó ningún patrón (use un patrón posicional o -f ARCHIVO)", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    non_empty = [p for p in raw_patterns if p]
    if not non_empty:
        msg = ("el archivo de patrones está vacío o solo contiene líneas vacías"
               if args.file else "el patrón no puede ser una cadena vacía")
        print(f"pygrep: {msg}", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    processed: list[str] = []
    for p in non_empty:
        if args.fixed_strings:
            p = re.escape(p)
        if args.word_regexp:
            p = rf"(?<!\w){p}(?!\w)"
        processed.append(p)

    pattern_str = processed[0] if len(processed) == 1 else "|".join(processed)

    if detect_redos(pattern_str):
        msg = (
            f"pygrep: ADVERTENCIA - patrón con quantifiers anidados detectado. "
            f"Puede causar ReDoS con ciertas entradas.\n"
            f"  Patrón: {pattern_str}\n"
            f"  Use --redos-strict para rechazar estos patrones."
        )
        if args.redos_strict:
            print(f"pygrep: patrón rechazado por --redos-strict: {pattern_str}", file=sys.stderr)
            sys.exit(ExitCode.ERROR)
        print(msg, file=sys.stderr)

    # Determinar flags de sensibilidad a mayúsculas
    if args.ignore_case:
        flags = re.IGNORECASE
    elif args.smart_case and pattern_str == pattern_str.lower():
        # Patrón todo en minúsculas → comportarse como -i
        flags = re.IGNORECASE
    else:
        flags = 0
    try:
        return re.compile(pattern_str, flags)
    except re.error as e:
        print(f"pygrep: Expresión regular inválida: {e}", file=sys.stderr)
        sys.exit(ExitCode.ERROR)


def build_config(args: GrepArgs, multiple_inputs: bool) -> Config:
    """Crea un objeto de configuración inmutable 'Config' a partir de los argumentos analizados.
    
    Valida la validez de los argumentos (como que el contexto o el tail no sean negativos),
    verifica la codificación, inicializa la expresión regular, procesa el rango de tiempo
    si se proporciona, y determina si se deben mostrar los nombres de los archivos en la salida.
    """
    if args.max_count is not None and args.max_count < 0:
        print("pygrep: -m/--max-count no puede ser negativo", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    try:
        codecs.lookup(args.encoding)
    except LookupError:
        print(f"pygrep: codificación desconocida: '{args.encoding}'", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    pattern = build_pattern(args)

    # Compilar versión en bytes del patrón para la optimización mmap en --multiline.
    # Se elimina re.UNICODE (incompatible con patrones bytes) y re.LOCALE.
    # Si la codificación del patrón falla (ej. patrón con chars fuera del encoding del
    # fichero), se establece None y el modo multilinea usará el path de texto clásico.
    pattern_bytes: re.Pattern[bytes] | None = None
    if args.multiline:
        try:
            raw_bytes = pattern.pattern.encode(args.encoding)
            compat_flags = pattern.flags & ~(re.UNICODE | re.LOCALE)
            pattern_bytes = re.compile(raw_bytes, compat_flags)
        except (re.error, UnicodeEncodeError, LookupError):
            pattern_bytes = None

    before_ctx = after_ctx = 0
    if args.context is not None:
        if args.context < 0: print("pygrep: -C/--context no puede ser negativo", file=sys.stderr); sys.exit(ExitCode.ERROR)
        before_ctx = after_ctx = min(args.context, MAX_CONTEXT_LINES)
    if args.before_context is not None:
        if args.before_context < 0: print("pygrep: -B/--before-context no puede ser negativo", file=sys.stderr); sys.exit(ExitCode.ERROR)
        before_ctx = min(args.before_context, MAX_CONTEXT_LINES)
    if args.after_context is not None:
        if args.after_context < 0: print("pygrep: -A/--after-context no puede ser negativo", file=sys.stderr); sys.exit(ExitCode.ERROR)
        after_ctx = min(args.after_context, MAX_CONTEXT_LINES)

    if before_ctx == MAX_CONTEXT_LINES or after_ctx == MAX_CONTEXT_LINES:
        print(f"pygrep: contexto truncado a {MAX_CONTEXT_LINES} líneas (límite de seguridad)", file=sys.stderr)

    use_color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty())
    max_depth: int | None = None if args.recursive else 1

    if args.no_filename:
        show_filename = False
    elif args.with_filename:
        show_filename = True
    else:
        show_filename = multiple_inputs

    valid_formats = ("text", "json", "csv")
    if args.output_format not in valid_formats:
        print(f"pygrep: formato inválido '{args.output_format}'. Use: {', '.join(valid_formats)}", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    if args.tail is not None and args.tail < 0:
        print("pygrep: --tail no puede ser negativo", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    time_range: tuple[datetime.datetime, datetime.datetime] | None = None
    if args.time_range is not None:
        start_str, end_str = args.time_range
        dt_start = parse_datetime_arg(start_str)
        dt_end   = parse_datetime_arg(end_str)
        if dt_start is None:
            print(f"pygrep: --time-range: timestamp de inicio inválido: '{start_str}'", file=sys.stderr)
            sys.exit(ExitCode.ERROR)
        if dt_end is None:
            print(f"pygrep: --time-range: timestamp de fin inválido: '{end_str}'", file=sys.stderr)
            sys.exit(ExitCode.ERROR)
        if dt_start > dt_end:
            print("pygrep: --time-range: el inicio debe ser anterior al fin", file=sys.stderr)
            sys.exit(ExitCode.ERROR)
        time_range = (dt_start, dt_end)

    if args.follow:
        incompatibles = (
            args.count or args.stats or args.summary or 
            args.tail is not None or args.time_range is not None or 
            args.output is not None or args.recursive or
            args.files_with_matches or args.files_without_matches
        )
        if incompatibles:
            print(
                "pygrep: --follow no es compatible con -c, --stats, --summary, "
                "--tail, --time-range, --output, -r, -l ni -L",
                file=sys.stderr
            )
            sys.exit(ExitCode.ERROR)

    # Parsing del filtro clave=valor
    kv_filter_compiled: tuple[tuple[str, re.Pattern[str]], ...] | None = None
    if args.kv_filter is not None:
        try:
            kv_filter_compiled = tuple(parse_kv_filter(args.kv_filter))
        except ValueError as e:
            print(f"pygrep: {e}", file=sys.stderr)
            sys.exit(ExitCode.ERROR)

    if (args.kv_mode or args.kv_filter is not None) and args.multiline:
        print("pygrep: --kv/--key-value no es compatible con --multiline/-U", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    # Parsing del filtro JSON
    json_filter_compiled: tuple[tuple[str, re.Pattern[str]], ...] | None = None
    if args.json_filter is not None:
        try:
            json_filter_compiled = tuple(parse_json_filter(args.json_filter))
        except ValueError as e:
            print(f"pygrep: {e}", file=sys.stderr)
            sys.exit(ExitCode.ERROR)

    if (args.json_mode or args.json_filter is not None) and args.multiline:
        print("pygrep: --json no es compatible con --multiline/-U", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    # Validación de --rate
    if args.rate_interval is not None:
        val = args.rate_interval.strip().lower()
        # Permitir formatos como '1s', '10s', '1m', '5m', '1h' etc
        if not re.match(r'^\d+[smh]$', val) and val not in ('s', 'm', 'h'):
            print(f"pygrep: intervalo de tasa inválido '{args.rate_interval}'. Debe ser un número seguido de s, m, o h (ej: 10s, 5m, 1h).", file=sys.stderr)
            sys.exit(ExitCode.ERROR)

    # Validación de --window / --threshold / --rate
    if args.threshold is not None and args.window_minutes is None and args.rate_interval is None:
        print("pygrep: --threshold requiere --window MINUTOS o --rate INTERVALO.", file=sys.stderr)
        sys.exit(ExitCode.ERROR)
    if args.window_minutes is not None and args.threshold is None:
        print("pygrep: --window requiere --threshold N.", file=sys.stderr)
        sys.exit(ExitCode.ERROR)
    if args.window_minutes is not None and args.window_minutes <= 0:
        print("pygrep: --window debe ser un entero positivo (minutos).", file=sys.stderr)
        sys.exit(ExitCode.ERROR)
    if args.threshold is not None and args.threshold <= 0:
        print("pygrep: --threshold debe ser un entero positivo.", file=sys.stderr)
        sys.exit(ExitCode.ERROR)

    return Config(
        pattern=pattern,
        pattern_bytes=pattern_bytes,
        smart_case=args.smart_case,
        invert_match=args.invert_match,
        count_only=args.count,
        line_number=args.line_number,
        max_depth=max_depth,
        use_color=use_color,
        show_filename=show_filename,
        before_context=before_ctx,
        after_context=after_ctx,
        max_count=args.max_count,
        files_with_matches=args.files_with_matches,
        files_without_matches=args.files_without_matches,
        encoding=args.encoding,
        show_stats=args.stats,
        unique=args.unique,
        include_patterns=tuple(args.include) if args.include else (),
        exclude_patterns=tuple(args.exclude) if args.exclude else (),
        ignore_dirs=tuple(args.ignore_dir) if args.ignore_dir else (),
        output_file=args.output,
        output_format=args.output_format,
        search_zip=args.search_zip,
        extract=args.extract,
        show_summary=args.summary,
        multiline=args.multiline,
        tail=args.tail,
        time_range=time_range,
        auto_encoding=args.auto_encoding,
        follow=args.follow,
        kv_mode=args.kv_mode,
        kv_filter=kv_filter_compiled,
        kv_skip_non_kv=args.kv_skip_non_kv,
        json_mode=args.json_mode,
        json_filter=json_filter_compiled,
        json_skip_non_json=args.json_skip_non_json,
        rate_interval=args.rate_interval,
        window_minutes=args.window_minutes,
        threshold=args.threshold,
    )


def setup_argparse() -> argparse.ArgumentParser:
    """Configura y devuelve el analizador de argumentos de línea de comandos (ArgumentParser).
    
    Define las opciones clásicas de grep (como -i, -v, -c, -n, -r, -w, -F, entre otras),
    así como las opciones de análisis avanzado del clon (como --stats, --summary,
    --tail, --time-range, --unique, etc.).
    """
    parser = argparse.ArgumentParser(
        prog="pygrep",
        description="Busca PATRÓN en ARCHIVOS, DIRECTORIOS o stdin.",
        add_help=False,
    )
    parser.add_argument("-?", "--help", action="help", default=argparse.SUPPRESS, help="Mostrar ayuda")
    parser.add_argument("-V", "--version", action="version", version="%(prog)s 1.5.0", help="Mostrar versión")

    # Argumentos posicionales
    parser.add_argument("pattern", nargs="?", default=None, help="Patrón (regex). Opcional con -f.")
    parser.add_argument("files",   nargs="*", default=["-"], help="Archivos/Directorios ('-' = stdin)")

    # Opciones clásicas
    grp_classic = parser.add_argument_group("Opciones de búsqueda")
    grp_classic.add_argument("-f", "--file",         default=None, metavar="ARCHIVO", help="Patrones desde archivo")
    grp_classic.add_argument("-i", "--ignore-case",  action="store_true", help="Ignora mayúsculas/minúsculas")
    grp_classic.add_argument("-S", "--smart-case",   action="store_true", dest="smart_case",
                             help="Búsqueda inteligente: ignora mayúsculas si el patrón es todo minúsculas; sensible si contiene alguna mayúscula")
    grp_classic.add_argument("-v", "--invert-match", action="store_true", help="Invierte coincidencia")
    grp_classic.add_argument("-c", "--count",        action="store_true", help="Solo conteo de coincidencias")
    grp_classic.add_argument("-n", "--line-number",  action="store_true", help="Mostrar número de línea")
    grp_classic.add_argument("-r", "--recursive",    action="store_true", help="Recursión profunda en directorios")
    grp_classic.add_argument("-w", "--word-regexp",  action="store_true", help="Coincidencia de palabras completas")
    grp_classic.add_argument("-F", "--fixed-strings",action="store_true", help="Tratar patrón como texto literal")
    grp_classic.add_argument("-E", "--extended-regexp", action="store_true", help="Compatibilidad con ERE (no operativo, Python usa RE por defecto)")
    grp_classic.add_argument("--color",    choices=["auto", "always", "never"], default="auto", help="Control de colores")
    grp_classic.add_argument("--encoding", default="utf-8", metavar="ENC", help="Codificación de los ficheros (default: utf-8)")
    grp_classic.add_argument("--auto-encoding", action="store_true", dest="auto_encoding",
                             help="Detectar automáticamente el encoding de cada fichero (usa charset-normalizer)")
    grp_classic.add_argument("--redos-strict", action="store_true", help="Rechazar patrones con riesgo de ReDoS")
    grp_classic.add_argument("-m", "--max-count",      type=int, default=None, metavar="NUM", help="Límite de coincidencias por fichero")
    grp_classic.add_argument("-A", "--after-context",  type=int, default=None, metavar="N",   help="N líneas de contexto después")
    grp_classic.add_argument("-B", "--before-context", type=int, default=None, metavar="N",   help="N líneas de contexto antes")
    grp_classic.add_argument("-C", "--context",        type=int, default=None, metavar="N",   help="N líneas de contexto simétrico")
    grp_classic.add_argument("-l", "--files-with-matches",   action="store_true", dest="files_with_matches",   help="Solo nombres de ficheros con coincidencia")
    grp_classic.add_argument("-L", "--files-without-match",  action="store_true", dest="files_without_matches", help="Solo nombres de ficheros sin coincidencia")
    grp_classic.add_argument("-h", "--no-filename",  action="store_true", dest="no_filename",  help="Suprimir nombre de fichero en la salida")
    grp_classic.add_argument("-H", "--with-filename", action="store_true", dest="with_filename", help="Forzar nombre de fichero en la salida")
    grp_classic.add_argument("-z", "--search-zip",   action="store_true", help="Buscar en archivos comprimidos (gzip, bzip2, lzma/xz, zip, tar, tar.gz, tgz, tar.bz2, tar.xz)")
    grp_classic.add_argument("-o", "--extract", "--only-matching", action="store_true", help="Mostrar solo la parte de la línea que coincide con el patrón")
    grp_classic.add_argument("-U", "--multiline", action="store_true", help="Permitir coincidencias de patrones que abarquen múltiples líneas")

    # Nuevas funcionalidades
    grp_adv = parser.add_argument_group("Análisis avanzado")
    grp_adv.add_argument(
        "--stats", action="store_true",
        help="Mostrar estadísticas de búsqueda al finalizar (en stderr)",
    )
    grp_adv.add_argument(
        "--summary", action="store_true",
        help="Mostrar un resumen corto de una línea al finalizar (en stderr)",
    )
    grp_adv.add_argument(
        "--tail", type=int, default=None, metavar="N",
        help="Mostrar solo las últimas N coincidencias del patrón",
    )
    grp_adv.add_argument(
        "--time-range", nargs=2, default=None, metavar=("INICIO", "FIN"), dest="time_range",
        help=(
            "Filtrar coincidencias por rango de timestamp. Formatos soportados: "
            "'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS', 'DD/Mon/YYYY:HH:MM:SS', 'Mon DD HH:MM:SS'. "
            "Ejemplo: --time-range '2026-05-26 10:00' '2026-05-26 12:00'"
        ),
    )
    grp_adv.add_argument(
        "-u", "--unique", action="store_true",
        help="Mostrar solo coincidencias únicas, eliminando duplicados",
    )
    grp_adv.add_argument(
        "--include", action="append", default=[], metavar="PATRÓN",
        help="Incluir solo ficheros que coincidan (ej: '*.log'). Repetible.",
    )
    grp_adv.add_argument(
        "--exclude", action="append", default=[], metavar="PATRÓN",
        help="Excluir ficheros que coincidan (ej: '*.bak'). Repetible.",
    )
    grp_adv.add_argument(
        "--ignore-dir", action="append", default=[], metavar="DIR",
        help="Ignorar directorios con este nombre (ej: .git). Repetible.",
    )
    grp_adv.add_argument(
        "--output", default=None, metavar="FICHERO",
        help="Guardar resultados en FICHERO (además de stdout)",
    )
    grp_adv.add_argument(
        "--format", dest="output_format",
        choices=["text", "json", "csv"], default="text",
        help="Formato del fichero de salida: text (default), json, csv",
    )
    grp_adv.add_argument(
    "--follow", action="store_true",
    help="Seguir el archivo en tiempo real (similar a tail -f)"
)

    # Logs estructurados
    grp_struct = parser.add_argument_group("Logs estructurados")
    grp_struct.add_argument(
        "--kv", "--key-value", action="store_true", dest="kv_mode",
        help=(
            "Activar parsing de l\u00edneas con formato clave=valor "
            "(systemd, nginx, logs personalizados). "
            "Combinar con --kv-filter para filtrar por campos espec\u00edficos."
        ),
    )
    grp_struct.add_argument(
        "--kv-filter", default=None, metavar="EXPR", dest="kv_filter",
        help=(
            "Filtrar l\u00edneas por pares clave:patr\u00f3n. "
            "Formato: 'clave:patr\u00f3n,clave2:patr\u00f3n2'. Los patrones son regex (insensibles). "
            "Conveniencia: 5xx -> 5\\d\\d. "
            "Ejemplo: --kv-filter 'level:error,status:5xx'"
        ),
    )
    grp_struct.add_argument(
        "--kv-skip", action="store_true", dest="kv_skip_non_kv",
        help="Omitir l\u00edneas que no contengan ning\u00fan par clave=valor (requiere --kv o --kv-filter)",
    )
    grp_struct.add_argument(
        "--json", action="store_true", dest="json_mode",
        help="Activar parsing de l\u00edneas en formato JSON estructurado."
    )
    grp_struct.add_argument(
        "--json-filter", default=None, metavar="EXPR", dest="json_filter",
        help=(
            "Filtrar l\u00edneas JSON por clave:patr\u00f3n. "
            "Formato: 'clave:patr\u00f3n,clave2:patr\u00f3n2'. Los patrones son regex (insensibles). "
            "Conveniencia: 5xx -> 5\\d\\d. "
            "Ejemplo: --json-filter 'level:error,status:5xx'"
        )
    )
    grp_struct.add_argument(
        "--json-skip", action="store_true", dest="json_skip_non_json",
        help="Omitir l\u00edneas que no sean un objeto JSON v\u00e1lido."
    )
    grp_struct.add_argument(
        "--rate", default=None, metavar="INTERVALO", dest="rate_interval",
        help=(
            "Calcular tasa de ocurrencias y mostrar histograma ASCII ordenado temporalmente. "
            "Intervalos soportados: un n\u00famero seguido de s (segundos), m (minutos) o h (horas). "
            "Ejemplo: --rate 10s, --rate 5m, --rate 1h"
        )
    )
    grp_struct.add_argument(
        "--window", type=int, default=None, metavar="MINUTOS", dest="window_minutes",
        help=(
            "Ventana deslizante (en minutos) para detectar picos de ocurrencias. "
            "Requiere --threshold. Ejemplo: --window 5 --threshold 10"
        )
    )
    grp_struct.add_argument(
        "--threshold", type=int, default=None, metavar="N", dest="threshold",
        help=(
            "Número máximo de coincidencias permitidas en la ventana --window. "
            "Si se supera, se emite una alerta en stderr. Requiere --window."
        )
    )

    return parser
