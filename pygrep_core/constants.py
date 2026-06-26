from enum import IntEnum
import re

class ExitCode(IntEnum):
    MATCH = 0
    NO_MATCH = 1
    ERROR = 2


COLOR_RESET      = "\033[0m"
COLOR_MATCH      = "\033[01;31m"
COLOR_FILENAME   = "\033[35m"
COLOR_LINENUM    = "\033[32m"
COLOR_SEPARATOR  = "\033[36m"
COLOR_STATS_HDR  = "\033[01;36m"
COLOR_STATS_VAL  = "\033[01;33m"

# Límites de seguridad (Anti-DoS)
MAX_CONTEXT_LINES    = 10_000
MAX_GLOB_EXPANSION   = 50_000
MAX_PATTERN_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_PATTERN_LINES    = 100_000
MAX_UNIQUE_CACHE     = 1_000_000  # Máximo de líneas únicas en memoria

# SECURITY: Regex para eliminar secuencias de escape ANSI maliciosas
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[()][AB012]")

REDOS_HEURISTIC = re.compile(
    r"""
    \(                  # apertura de grupo
        [^()]*          # contenido sin paréntesis
        [+*]            # quantifier interno (+ o *)
    \)                  # cierre de grupo
    [+*]                # quantifier externo
    """,
    re.VERBOSE,
)

LOG_LEVEL_RE = re.compile(r"\b(DEBUG|INFO|INFORMATION|WARN|WARNING|ERROR|FATAL|CRITICAL|MAJOR|MINOR|CLEAR|CLEARED)\b", re.IGNORECASE)

# Key-Value pair extraction regex: key=value, key => value, key='quoted value', supporting commas
KV_RE = re.compile(
    r'(?P<key>\w[\w.\-]*)\s*(?:=>|=)\s*'
    r'(?P<value>"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[^,\s\(\)\{\}]+)'
)

# Formatos de timestamp soportados para --time-range (de más específico a menos)
TIMESTAMP_FMTS: list[str] = [
    "%Y-%m-%dT%H:%M:%S",  # ISO 8601 con T:   2026-05-26T10:30:00
    "%Y-%m-%d %H:%M:%S",  # ISO con espacio:  2026-05-26 10:30:00
    "%Y-%m-%d %H:%M",     # ISO sin segundos: 2026-05-26 10:30
    "%d/%b/%Y:%H:%M:%S",  # Apache:           26/May/2026:10:30:00
    "%b %d %H:%M:%S",     # Syslog:           May 26 10:30:00
]

# Pares (regex de detección en línea, formato strptime) para parse_timestamp
TIMESTAMP_RES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"),  "%Y-%m-%dT%H:%M:%S"),
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?"),  "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"),                   "%Y-%m-%d %H:%M"),
    (re.compile(r"\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}"),       "%d/%b/%Y:%H:%M:%S"),
    (re.compile(r"[A-Za-z]{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}"),         "%b %d %H:%M:%S"),
]
