import bisect
import mmap
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from pygrep_core.constants import MAX_UNIQUE_CACHE, LOG_LEVEL_RE
from pygrep_core.config import Config
from pygrep_core.parser_utils import parse_timestamp, parse_kv_line, kv_filter_matches, json_filter_matches
import json
from pygrep_core.output import (
    MatchRecord,
    MatchStats,
    format_filename,
    safe_print,
    format_and_print_event,
    sanitize_string,
)


@dataclass(frozen=True)
class OutputEvent:
    line_num: int | None
    content: str
    is_match: bool | None
    match_span: tuple[int, int] | None = None


def search_stream(
    stream: Iterator[str],
    config: Config,
    seen: set[str] | None = None,
    counter: list[int] | None = None,
    start_line: int = 1,
) -> Iterator[OutputEvent]:
    """Genera OutputEvent de coincidencia o contexto para cada línea relevante del flujo de entrada.
    
    Procesa las líneas aplicando lógica de contexto anterior/posterior (before/after),
    filtrado por fecha si se define, límite de matches (max_count), coincidencia invertida,
    y control de duplicados mediante la estructura `seen`.
    """
    before, after = config.before_context, config.after_context
    before_buffer: deque[tuple[int, str]] = deque(maxlen=before) if before > 0 else deque()
    current_group: list[tuple[int, str, bool]] = []
    last_match_line = -1
    has_emitted = False
    matches_found = 0

    if config.extract:
        for line_num, raw_line in enumerate(stream, start=start_line):
            if counter is not None:
                counter[0] = line_num
            clean = raw_line.rstrip("\n").rstrip("\r")

            # KV mode filtering (modo extract)
            if config.kv_mode or config.kv_filter is not None:
                _kv = parse_kv_line(clean)
                if config.kv_skip_non_kv and not _kv:
                    continue
                if config.kv_filter is not None and not kv_filter_matches(_kv, config.kv_filter):
                    continue

            # JSON mode filtering (modo extract)
            if config.json_mode or config.json_filter is not None:
                try:
                    _json = json.loads(clean)
                    if not isinstance(_json, dict):
                        # Si no es un diccionario, no podemos filtrar por clave
                        if config.json_skip_non_json:
                            continue
                        _json = {}
                except json.JSONDecodeError:
                    if config.json_skip_non_json:
                        continue
                    _json = {}
                if config.json_filter is not None and not json_filter_matches(_json, config.json_filter):
                    continue

            if config.time_range is not None:
                _ts = parse_timestamp(clean)
                if _ts is None or not (config.time_range[0] <= _ts <= config.time_range[1]):
                    continue

            if config.max_count is not None and matches_found >= config.max_count:
                break
                
            if not config.invert_match:
                for match in config.pattern.finditer(clean):
                    matched_text = match.group(0)
                    if not matched_text:
                        continue
                    if seen is not None:
                        if matched_text in seen:
                            continue
                        if len(seen) < MAX_UNIQUE_CACHE:
                            seen.add(matched_text)
                    
                    matches_found += 1
                    if counter is not None:
                        counter[1] = matches_found
                    
                    yield OutputEvent(line_num=line_num, content=matched_text, is_match=True)
                    if config.max_count is not None and matches_found >= config.max_count:
                        break
            else:
                if not bool(config.pattern.search(clean)):
                    if seen is not None:
                        if clean in seen:
                            continue
                        if len(seen) < MAX_UNIQUE_CACHE:
                            seen.add(clean)
                    
                    matches_found += 1
                    if counter is not None:
                        counter[1] = matches_found
                    
                    yield OutputEvent(line_num=line_num, content=clean, is_match=True)
                    if config.max_count is not None and matches_found >= config.max_count:
                        break
        return

    def flush(emit_sep: bool) -> Iterator[OutputEvent]:
        nonlocal current_group, has_emitted
        if not current_group:
            return
        if emit_sep and has_emitted and (before > 0 or after > 0):
            yield OutputEvent(line_num=None, content="", is_match=None)
        for ln, content, is_m in current_group:
            yield OutputEvent(line_num=ln, content=content, is_match=is_m)
        has_emitted = True
        current_group = []

    for line_num, raw_line in enumerate(stream, start=start_line):
        if counter is not None:
            counter[0] = line_num

        clean = raw_line.rstrip("\n").rstrip("\r")
        is_match = (
            (config.max_count is None or matches_found < config.max_count)
            and bool(config.pattern.search(clean))
        )
        if config.invert_match:
            is_match = not is_match

        # KV mode filtering: fuerza is_match=False para respetar el buffering de contexto
        if is_match and (config.kv_mode or config.kv_filter is not None):
            _kv = parse_kv_line(clean)
            if config.kv_skip_non_kv and not _kv:
                is_match = False
            elif config.kv_filter is not None and not kv_filter_matches(_kv, config.kv_filter):
                is_match = False

        # JSON mode filtering: fuerza is_match=False para respetar el buffering de contexto
        if is_match and (config.json_mode or config.json_filter is not None):
            try:
                _json = json.loads(clean)
                if not isinstance(_json, dict):
                    if config.json_skip_non_json:
                        is_match = False
                    _json = {}
            except json.JSONDecodeError:
                if config.json_skip_non_json:
                    is_match = False
                _json = {}
            if is_match and config.json_filter is not None and not json_filter_matches(_json, config.json_filter):
                is_match = False

        if is_match and seen is not None:
            if clean in seen:
                is_match = False
            elif len(seen) < MAX_UNIQUE_CACHE:
                seen.add(clean)

        if is_match and config.time_range is not None:
            _ts = parse_timestamp(clean)
            if _ts is None or not (config.time_range[0] <= _ts <= config.time_range[1]):
                is_match = False

        if is_match:
            matches_found += 1
            if counter is not None:
                counter[1] = matches_found
            if before == 0 and after == 0:
                yield OutputEvent(line_num=line_num, content=clean, is_match=True)
            else:
                if not current_group and before > 0:
                    current_group.extend((ln, ctx, False) for ln, ctx in before_buffer)
                elif current_group and before > 0:
                    last_in = current_group[-1][0]
                    current_group.extend((ln, ctx, False) for ln, ctx in before_buffer if ln > last_in)

                current_group.append((line_num, clean, True))
                last_match_line = line_num
                before_buffer.clear()
        else:
            if before > 0:
                before_buffer.append((line_num, clean))
            if current_group and after > 0 and line_num <= last_match_line + after:
                current_group.append((line_num, clean, False))
            elif current_group:
                yield from flush(emit_sep=(before > 0 or after > 0))

        if config.max_count is not None and matches_found >= config.max_count:
            break

    yield from flush(emit_sep=False)


def process_stream(
    stream: Iterator[str],
    file_path: Path | None,
    config: Config,
    seen: set[str] | None,
    records: list[MatchRecord],
    stats: MatchStats | None = None,
    start_line: int = 1,
) -> tuple[int, int]:
    """Procesa un flujo de texto, busca coincidencias y realiza la salida de los resultados.
    
    Lee el flujo línea a línea o todo de golpe si la opción multilínea está activa.
    Actualiza el registro de resultados `records` para exportación y recopila métricas
    en `stats`. Retorna una tupla con (match_count, line_count).
    """
    if config.multiline:
        content = "".join(stream)
        lines = content.splitlines(keepends=True)
        line_starts = []
        current_offset = 0
        for line in lines:
            line_starts.append(current_offset)
            current_offset += len(line)

        def get_line_num(char_index: int) -> int:
            return bisect.bisect_right(line_starts, char_index)

        matches_list = list(config.pattern.finditer(content))
        if config.tail is not None:
            matches_list = matches_list[-config.tail:] if config.tail > 0 else []
        matches_found = 0

        if config.files_with_matches or config.files_without_matches:
            return len(matches_list), len(lines)

        if config.count_only:
            prefix = f"{format_filename(file_path)}:" if config.show_filename and file_path is not None else ""
            safe_print(f"{prefix}{len(matches_list)}")
            return len(matches_list), len(lines)

        for match in matches_list:
            if config.max_count is not None and matches_found >= config.max_count:
                break

            start_idx, end_idx = match.span()
            start_line = get_line_num(start_idx)
            end_line = get_line_num(end_idx - 1) if end_idx > start_idx else start_line

            for ln in range(start_line, end_line + 1):
                line_content = lines[ln - 1].rstrip("\r\n")

                if seen is not None:
                    if line_content in seen:
                        continue
                    if len(seen) < MAX_UNIQUE_CACHE:
                        seen.add(line_content)

                line_start_offset = line_starts[ln - 1]
                match_start = max(start_idx, line_start_offset) - line_start_offset
                match_end = min(end_idx, line_start_offset + len(line_content)) - line_start_offset
                span = (match_start, match_end) if match_end > match_start else None

                event = OutputEvent(line_num=ln, content=line_content, is_match=True, match_span=span)

                if (config.output_file or config.rate_interval or (config.window_minutes is not None and config.threshold is not None)) and file_path is not None:
                    records.append(MatchRecord(
                        file=format_filename(file_path),
                        line_num=ln,
                        content=sanitize_string(line_content),
                    ))

                if stats is not None and config.show_summary:
                    m_level = LOG_LEVEL_RE.search(line_content)
                    if m_level:
                        level = m_level.group(1).upper()
                        if level == "WARNING":
                            level = "WARN"
                        elif level == "INFORMATION":
                            level = "INFO"
                        elif level == "CLEARED":
                            level = "CLEAR"
                        if level in stats.log_level_counts:
                            stats.log_level_counts[level] += 1

                if not config.show_summary and not config.rate_interval:
                    format_and_print_event(event, file_path, config)

            matches_found += 1

        return matches_found, len(lines)

    counter: list[int] = [0, 0]  # [line_count, match_count]
    matches = 0

    if config.tail is not None:
        all_events = list(search_stream(stream, config, seen, counter, start_line))
        match_positions = [i for i, ev in enumerate(all_events) if ev.is_match is True]
        if config.tail > 0 and match_positions:
            first_kept = match_positions[max(0, len(match_positions) - config.tail)]
            tail_events: list[OutputEvent] = all_events[first_kept:]
        else:
            tail_events = []
        for event in tail_events:
            if event.is_match is True:
                matches += 1
                if (config.output_file or config.rate_interval or (config.window_minutes is not None and config.threshold is not None)) and file_path is not None:
                    records.append(MatchRecord(
                        file=format_filename(file_path),
                        line_num=event.line_num,
                        content=sanitize_string(event.content),
                    ))
                if stats is not None and config.show_summary:
                    _m = LOG_LEVEL_RE.search(event.content)
                    if _m:
                        level = _m.group(1).upper()
                        if level == "WARNING":
                            level = "WARN"
                        elif level == "INFORMATION":
                            level = "INFO"
                        elif level == "CLEARED":
                            level = "CLEAR"
                        if level in stats.log_level_counts:
                            stats.log_level_counts[level] += 1
            if not config.count_only and not config.files_with_matches and not config.files_without_matches and not config.show_summary and not config.rate_interval:
                format_and_print_event(event, file_path, config)
    else:
        for event in search_stream(stream, config, seen, counter, start_line):
            if event.is_match is True:
                matches += 1
                if (config.output_file or config.rate_interval or (config.window_minutes is not None and config.threshold is not None)) and file_path is not None:
                    records.append(MatchRecord(
                        file=format_filename(file_path),
                        line_num=event.line_num,
                        content=sanitize_string(event.content),
                    ))
                if stats is not None and config.show_summary:
                    m = LOG_LEVEL_RE.search(event.content)
                    if m:
                        level = m.group(1).upper()
                        if level == "WARNING":
                            level = "WARN"
                        elif level == "INFORMATION":
                            level = "INFO"
                        elif level == "CLEARED":
                            level = "CLEAR"
                        if level in stats.log_level_counts:
                            stats.log_level_counts[level] += 1
            if not config.count_only and not config.files_with_matches and not config.files_without_matches and not config.show_summary and not config.rate_interval:
                format_and_print_event(event, file_path, config)

    line_count = counter[0]

    if config.count_only:
        prefix = f"{format_filename(file_path)}:" if config.show_filename and file_path is not None else ""
        safe_print(f"{prefix}{matches}")

    return matches, line_count

def follow_stream(path: Path, config: Config) -> Iterator[str]:
    """Generador que emite líneas nuevas de un archivo en tiempo real."""
    try:
        with open(path, "r", encoding=config.encoding, errors="replace") as f:
            f.seek(0, os.SEEK_END)  # Posicionarse al final del archivo
            while True:
                line = f.readline()
                if line:
                    yield line
                else:
                    f.seek(f.tell())  # Limpiar estado EOF y buffer interno
                    time.sleep(0.1)  # Polling suave (bajo consumo CPU)
    except KeyboardInterrupt:
        return
    except Exception as e:
        print(f"\npygrep: error siguiendo {path}: {e}", file=sys.stderr)
        return


def process_multiline_mmap(
    path: Path,
    config: Config,
    seen: set[str] | None,
    records: list[MatchRecord],
    stats: MatchStats | None,
) -> tuple[int, int]:
    """Búsqueda multilinea usando mmap: evita cargar el archivo completo en RAM como str.

    Mapea el archivo en memoria virtual con mmap.ACCESS_READ y ejecuta la búsqueda
    regex directamente sobre los bytes mapeados (sin decodificar todo el archivo).
    El SO gestiona el paginado bajo demanda: en archivos grandes, solo las páginas
    accedidas se cargan en RAM física, reduciendo el uso de memoria de O(n) a O(k)
    donde k es el tamaño del área cubierta por las coincidencias.

    Solo decodifica las líneas individuales que contienen coincidencias, no el
    archivo completo. Esto es significativamente más eficiente en RAM para archivos
    grandes con pocas coincidencias dispersas.

    Precondición: config.pattern_bytes no es None y el archivo ya se verificó
    como texto (no binario) por open_file_safely().

    Retorna (match_count, line_count).
    """
    assert config.pattern_bytes is not None
    encoding = config.encoding

    try:
        with open(path, "rb") as f:
            # Obtener tamaño; archivos vacíos no se pueden mapear
            file_size = f.seek(0, 2)
            if file_size == 0:
                return 0, 0
            f.seek(0)

            try:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except (ValueError, OSError) as exc:
                # mmap no disponible en este sistema/fichero; el llamante
                # debería reintentar con el path de texto estándar.
                raise OSError(f"mmap no disponible: {exc}") from exc

            with mm:
                # --- Índice de posiciones de inicio de línea (en bytes) ---
                # Escaneamos b'\n' directamente en el mmap sin decodificar nada.
                line_starts: list[int] = [0]
                scan_pos = 0
                while True:
                    nl_idx = mm.find(b"\n", scan_pos)
                    if nl_idx == -1:
                        break
                    line_starts.append(nl_idx + 1)
                    scan_pos = nl_idx + 1
                total_lines = len(line_starts)

                def get_line_num(byte_offset: int) -> int:
                    """Número de línea 1-based para un offset de byte dado."""
                    return bisect.bisect_right(line_starts, byte_offset)

                # --- Búsqueda directa en bytes del mmap (sin decodificar) ---
                matches_list = list(config.pattern_bytes.finditer(mm))
                if config.tail is not None:
                    matches_list = (
                        matches_list[-config.tail:] if config.tail > 0 else []
                    )

                # Atajos rápidos que no necesitan decodificar líneas
                if config.files_with_matches or config.files_without_matches:
                    return len(matches_list), total_lines

                if config.count_only:
                    prefix = f"{format_filename(path)}:" if config.show_filename else ""
                    safe_print(f"{prefix}{len(matches_list)}")
                    return len(matches_list), total_lines

                matches_found = 0

                for m in matches_list:
                    if config.max_count is not None and matches_found >= config.max_count:
                        break

                    start_b, end_b = m.span()
                    start_ln = get_line_num(start_b)
                    end_ln = get_line_num(end_b - 1) if end_b > start_b else start_ln

                    for ln in range(start_ln, end_ln + 1):
                        line_start_b = line_starts[ln - 1]
                        # Límite del contenido de la línea: justo antes del '\n'
                        # de la siguiente línea, o fin del archivo.
                        line_end_b = (
                            line_starts[ln] - 1 if ln < len(line_starts) else file_size
                        )
                        # rstrip b'\r' para manejar archivos CRLF (Windows)
                        raw_bytes = mm[line_start_b:line_end_b].rstrip(b"\r")
                        line_content = raw_bytes.decode(encoding, errors="replace")

                        if seen is not None:
                            if line_content in seen:
                                continue
                            if len(seen) < MAX_UNIQUE_CACHE:
                                seen.add(line_content)

                        # Convertir offsets de bytes a offsets de caracteres para
                        # coloreado ANSI preciso (necesario con contenido UTF-8
                        # multibyte: el nº de bytes != nº de chars).
                        byte_ms = max(start_b, line_start_b) - line_start_b
                        byte_me = (
                            min(end_b, line_start_b + len(raw_bytes)) - line_start_b
                        )
                        if byte_me > byte_ms:
                            char_ms = len(
                                raw_bytes[:byte_ms].decode(encoding, errors="replace")
                            )
                            char_me = len(
                                raw_bytes[:byte_me].decode(encoding, errors="replace")
                            )
                            span: tuple[int, int] | None = (
                                (char_ms, char_me) if char_me > char_ms else None
                            )
                        else:
                            span = None

                        event = OutputEvent(
                            line_num=ln,
                            content=line_content,
                            is_match=True,
                            match_span=span,
                        )

                        if (
                            config.output_file
                            or config.rate_interval
                            or (
                                config.window_minutes is not None
                                and config.threshold is not None
                            )
                        ):
                            records.append(MatchRecord(
                                file=format_filename(path),
                                line_num=ln,
                                content=sanitize_string(line_content),
                            ))

                        if stats is not None and config.show_summary:
                            m_level = LOG_LEVEL_RE.search(line_content)
                            if m_level:
                                level = m_level.group(1).upper()
                                if level == "WARNING":
                                    level = "WARN"
                                elif level == "INFORMATION":
                                    level = "INFO"
                                elif level == "CLEARED":
                                    level = "CLEAR"
                                if level in stats.log_level_counts:
                                    stats.log_level_counts[level] += 1

                        if not config.show_summary and not config.rate_interval:
                            format_and_print_event(event, path, config)

                    matches_found += 1

                return matches_found, total_lines

    except PermissionError:
        print(f"pygrep: {path}: Permiso denegado", file=sys.stderr)
        return 0, 0
    except OSError as e:
        print(f"pygrep: {path}: {e}", file=sys.stderr)
        return 0, 0
