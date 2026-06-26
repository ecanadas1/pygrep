import datetime
import re
import warnings
from pygrep_core.constants import REDOS_HEURISTIC, TIMESTAMP_FMTS, TIMESTAMP_RES, KV_RE

def detect_redos(pattern: str) -> bool:
    """Retorna True si el patrón parece tener riesgo de ReDoS usando una heurística simple."""
    return bool(REDOS_HEURISTIC.search(pattern))


def parse_timestamp(text: str) -> datetime.datetime | None:
    """Extrae e interpreta el primer timestamp reconocible de una línea de log."""
    _year = datetime.datetime.now().year
    for pattern, fmt in TIMESTAMP_RES:
        m = pattern.search(text)
        if m:
            raw = m.group(0).split(".")[0]  # eliminar sub-segundos
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    dt = datetime.datetime.strptime(raw, fmt)
                return dt.replace(year=_year) if "%Y" not in fmt else dt
            except ValueError:
                continue
    return None


def parse_datetime_arg(value: str) -> datetime.datetime | None:
    """Parsea un string de fecha/hora introducido por el usuario en la CLI."""
    _year = datetime.datetime.now().year
    raw = value.split(".")[0]  # strip microseconds si existen
    for fmt in TIMESTAMP_FMTS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                dt = datetime.datetime.strptime(raw, fmt)
            return dt.replace(year=_year) if "%Y" not in fmt else dt
        except ValueError:
            continue
    return None


def parse_kv_line(line: str) -> dict[str, str]:
    """Extrae todos los pares clave=valor de una línea de log.

    Soporta valores sin comillas, con comillas dobles y simples.
    Ejemplo: 'ts=2026 level=error msg="disk full"' →
    {'ts': '2026', 'level': 'error', 'msg': 'disk full'}
    """
    result: dict[str, str] = {}
    for m in KV_RE.finditer(line):
        key = m.group("key")
        val = m.group("value")
        # Eliminar comillas envolventes y resolver escapes básicos
        if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            val = val[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        elif len(val) >= 2 and val[0] == "'" and val[-1] == "'":
            val = val[1:-1].replace("\\'", "'").replace('\\\\', '\\')
        result[key] = val
    return result


def parse_kv_filter(expr: str) -> list[tuple[str, re.Pattern[str]]]:
    """Parsea una expresión de filtro KV: 'clave:patrón,clave2:patrón2'.

    Los patrones son expresiones regulares Python (insensibles a mayúsculas).
    Conveniencia: 'x' que sigue a un dígito se convierte a '\\d'
    (ej: 5xx → 5\\d\\d, 4xx → 4\\d\\d).

    Retorna lista de (clave, regex_compilado).
    Lanza ValueError si la expresión o algún patrón es inválido.
    """
    pairs: list[tuple[str, re.Pattern[str]]] = []
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(
                f"Filtro KV inválido: '{part}'. Formato esperado: clave:patrón"
            )
        key, _, raw_val = part.partition(":")
        key = key.strip()
        if not key:
            raise ValueError(f"Filtro KV inválido: clave vacía en '{part}'")
        # Conveniencia: dígito seguido de 'x's → dígito seguido de '\d' por cada 'x'
        raw_strip = raw_val.strip()
        m_wildcard = re.match(r'^(\d+)(x+)$', raw_strip, re.IGNORECASE)
        if m_wildcard:
            digit = m_wildcard.group(1)
            xs = m_wildcard.group(2)
            val = digit + (r'\d' * len(xs))
        else:
            val = raw_strip
        try:
            compiled = re.compile(val, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Filtro KV: patrón regex inválido '{val}': {e}")
        pairs.append((key, compiled))
    return pairs


def kv_filter_matches(
    kv_data: dict[str, str],
    filters: tuple[tuple[str, re.Pattern[str]], ...],
) -> bool:
    """Retorna True si todos los filtros se cumplen en kv_data.

    Un filtro falla si la clave no existe en kv_data o si el patrón
    no encuentra coincidencia en el valor asociado.
    """
    for key, pattern in filters:
        val = kv_data.get(key)
        if val is None or not pattern.search(val):
            return False
    return True


def parse_json_filter(expr: str) -> list[tuple[str, re.Pattern[str]]]:
    """Parsea una expresión de filtro JSON: 'clave:patrón,clave2:patrón2'.

    Los patrones son expresiones regulares Python (insensibles a mayúsculas).
    Conveniencia: 'x' que sigue a un dígito se convierte a '\\d'
    (ej: 5xx → 5\\d\\d, 4xx → 4\\d\\d).

    Retorna lista de (clave, regex_compilado).
    Lanza ValueError si la expresión o algún patrón es inválido.
    """
    pairs: list[tuple[str, re.Pattern[str]]] = []
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(
                f"Filtro JSON inválido: '{part}'. Formato esperado: clave:patrón"
            )
        key, _, raw_val = part.partition(":")
        key = key.strip()
        if not key:
            raise ValueError(f"Filtro JSON inválido: clave vacía en '{part}'")
        # Conveniencia: dígito seguido de 'x's → dígito seguido de '\d' por cada 'x'
        raw_strip = raw_val.strip()
        m_wildcard = re.match(r'^(\d+)(x+)$', raw_strip, re.IGNORECASE)
        if m_wildcard:
            digit = m_wildcard.group(1)
            xs = m_wildcard.group(2)
            val = digit + (r'\d' * len(xs))
        else:
            val = raw_strip
        try:
            compiled = re.compile(val, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Filtro JSON: patrón regex inválido '{val}': {e}")
        pairs.append((key, compiled))
    return pairs


def json_filter_matches(
    json_data: dict[str, any],
    filters: tuple[tuple[str, re.Pattern[str]], ...],
) -> bool:
    """Retorna True si todos los filtros se cumplen en el objeto json_data.

    Soporta claves anidadas separadas por punto (ej: 'user.name').
    Un filtro falla si la clave no existe en json_data o si el patrón
    no encuentra coincidencia en el valor asociado (convertido a string).
    """
    for key_path, pattern in filters:
        # Resolver claves anidadas (ej. user.profile.name)
        parts = key_path.split(".")
        curr: any = json_data
        for p in parts:
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                curr = None
                break
        
        if curr is None:
            return False
            
        val_str = str(curr)
        if not pattern.search(val_str):
            return False
    return True

