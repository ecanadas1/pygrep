import bz2
import fnmatch
import glob as _glob
import gzip
import io
import lzma
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Sequence, Iterator

from pygrep_core.constants import MAX_GLOB_EXPANSION
from pygrep_core.config import Config

# We will dynamically import engine and output components to prevent circular imports if any,
# or we can import them directly if the structure is clean. Let's do direct imports:
# Since engine.process_stream handles search_stream and format_and_print_event,
# and output formats/prints events, let's keep references clean.


def file_matches_filter(path: Path, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    """True si el fichero debe procesarse según --include / --exclude."""
    name = path.name
    if include and not any(fnmatch.fnmatch(name, pat) for pat in include):
        return False
    if exclude and any(fnmatch.fnmatch(name, pat) for pat in exclude):
        return False
    return True


def dir_is_ignored(path: Path, ignore_dirs: tuple[str, ...]) -> bool:
    """True si algún componente de la ruta coincide con --ignore-dir."""
    return any(
        fnmatch.fnmatch(part, pat)
        for part in path.parts
        for pat in ignore_dirs
    )


def discover_files(paths: Sequence[str], max_depth: int | None, config: Config) -> Iterator[Path]:
    """Explora y genera de forma perezosa (lazy) las rutas de los archivos a procesar.
    
    Resuelve comodines (globs) y desciende recursivamente por los directorios hasta
    la profundidad especificada (`max_depth`), filtrando por inclusión/exclusión y
    excluyendo symlinks y directorios ignorados.
    """
    for p_str in paths:
        if p_str == "-":
            continue

        if any(c in p_str for c in "*?[]"):
            matched: list[str] = []
            for path in _glob.iglob(p_str, recursive=True):
                matched.append(path)
                if len(matched) >= MAX_GLOB_EXPANSION:
                    print(f"pygrep: ADVERTENCIA - expansión de comodines limitada a {MAX_GLOB_EXPANSION} rutas", file=sys.stderr)
                    break
            if not matched:
                matched = [p_str]
        else:
            matched = [p_str]

        for m in matched:
            p = Path(m)
            if p.is_symlink():
                continue  # SECURITY: Ignorar symlinks por defecto

            if p.is_dir():
                if config.ignore_dirs and dir_is_ignored(p, config.ignore_dirs):
                    continue
                if max_depth is None:
                    for f in p.rglob("*"):
                        if not f.is_file() or f.is_symlink():
                            continue
                        if config.ignore_dirs and dir_is_ignored(f.parent, config.ignore_dirs):
                            continue
                        if file_matches_filter(f, config.include_patterns, config.exclude_patterns):
                            yield f
                else:
                    try:
                        for entry in p.iterdir():
                            if entry.is_file() and not entry.is_symlink():
                                if file_matches_filter(entry, config.include_patterns, config.exclude_patterns):
                                    yield entry
                    except PermissionError:
                        print(f"pygrep: {p}: Permiso denegado", file=sys.stderr)
            elif p.is_file():
                if file_matches_filter(p, config.include_patterns, config.exclude_patterns):
                    yield p
            else:
                print(f"pygrep: {p}: No existe el archivo o directorio", file=sys.stderr)


def _detect_encoding(chunk: bytes, fallback: str) -> str:
    """Intenta detectar el encoding de un bloque de bytes con charset-normalizer.
    Devuelve el encoding detectado o el fallback si no puede determinarlo."""
    try:
        from charset_normalizer import from_bytes
        result = from_bytes(chunk).best()
        if result is not None:
            return str(result.encoding)
    except ImportError:
        pass
    return fallback


def open_file_safely(
    path: Path,
    config: "Config",
) -> tuple[io.TextIOWrapper | None, bool, bytes]:
    """Abre un fichero de forma segura detectando si es binario y el encoding.

    Si config.auto_encoding es True, usa charset-normalizer para detectar el
    encoding real del fichero antes de abrirlo. Si no, usa config.encoding.
    En cualquier caso, errors='replace' garantiza que un fallo residual de
    decodificación no rompa la búsqueda.
    """
    raw = path.open("rb")
    chunk = raw.read(8192)

    # Detección de binario: presencia de bytes nulos
    is_binary = b"\x00" in chunk
    if is_binary:
        raw.close()
        return None, True, chunk

    # Detección de encoding
    if config.auto_encoding:
        encoding = _detect_encoding(chunk, config.encoding)
        if encoding != config.encoding:
            print(
                f"pygrep: {path}: encoding detectado '{encoding}' "
                f"(configurado: '{config.encoding}')",
                file=sys.stderr,
            )
    else:
        encoding = config.encoding

    raw.seek(0)
    return io.TextIOWrapper(raw, encoding=encoding, errors="replace"), False, b""


def get_clean_internal_path(virtual_path: Path) -> Path:
    path_str = str(virtual_path).replace("\\", "/")
    if ":" in path_str:
        parts = path_str.split(":")
        if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
            nested_parts = parts[2:]
        else:
            nested_parts = parts[1:]
        if nested_parts:
            return Path(nested_parts[-1])
    return Path(virtual_path.name)


def process_file_recursive(
    virtual_path: Path,
    config: Config,
    seen: set[str] | None,
    records: list,
    stats=None,
    data: bytes | None = None,
) -> tuple[bool, bool, int, int]:
    """Procesa un archivo (real o en memoria) de manera recursiva si es comprimido/archivo."""
    from pygrep_core.output import format_filename, safe_print
    from pygrep_core.engine import process_stream

    if config.search_zip:
        name_lower = virtual_path.name.lower()
        suffix = virtual_path.suffix.lower()
        _TAR_EXTS = (
            ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.lzma",
            ".tgz", ".tbz2", ".txz",
        )
        is_tar = suffix == ".tar" or any(name_lower.endswith(ext) for ext in _TAR_EXTS)
        is_zip = suffix == ".zip"
        is_single_compressed = suffix in (".gz", ".bz2", ".xz", ".lzma")

        if is_zip:
            try:
                zip_src = io.BytesIO(data) if data is not None else virtual_path
                with zipfile.ZipFile(zip_src) as z:
                    any_match = False
                    any_error = False
                    total_match_count = 0
                    total_line_count = 0
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        try:
                            internal_name = info.filename
                        except Exception:
                            internal_name = info.filename.decode("utf-8", errors="replace")

                        nested_virtual_path = Path(f"{virtual_path}:{internal_name}")
                        try:
                            member_bytes = z.read(info)
                        except Exception as e:
                            print(f"pygrep: {virtual_path}:{internal_name}: error leyendo zip interno: {e}", file=sys.stderr)
                            any_error = True
                            continue

                        m_match, m_err, m_match_count, m_line_count = process_file_recursive(
                            nested_virtual_path, config, seen, records, stats, data=member_bytes
                        )
                        if m_match:
                            any_match = True
                            total_match_count += m_match_count
                        if m_err:
                            any_error = True
                        total_line_count += m_line_count
                    return any_match, any_error, total_match_count, total_line_count
            except Exception as e:
                print(f"pygrep: {virtual_path}: error leyendo zip: {e}", file=sys.stderr)
                return False, True, 0, 0

        elif is_tar:
            try:
                tar_src = io.BytesIO(data) if data is not None else None
                tar_args = {"name": virtual_path} if tar_src is None else {"fileobj": tar_src}
                with tarfile.open(mode="r:*", **tar_args) as t:
                    any_match = False
                    any_error = False
                    total_match_count = 0
                    total_line_count = 0
                    for member in t.getmembers():
                        if not member.isfile():
                            continue

                        internal_name = member.name
                        nested_virtual_path = Path(f"{virtual_path}:{internal_name}")

                        try:
                            raw_file = t.extractfile(member)
                        except Exception as e:
                            print(f"pygrep: {virtual_path}:{internal_name}: error extrayendo miembro: {e}", file=sys.stderr)
                            any_error = True
                            continue

                        if raw_file is None:
                            continue

                        with raw_file:
                            member_bytes = raw_file.read()

                        m_match, m_err, m_match_count, m_line_count = process_file_recursive(
                            nested_virtual_path, config, seen, records, stats, data=member_bytes
                        )
                        if m_match:
                            any_match = True
                            total_match_count += m_match_count
                        if m_err:
                            any_error = True
                        total_line_count += m_line_count
                    return any_match, any_error, total_match_count, total_line_count
            except Exception as e:
                print(f"pygrep: {virtual_path}: error leyendo tar: {e}", file=sys.stderr)
                return False, True, 0, 0

        elif is_single_compressed:
            try:
                src_file = io.BytesIO(data) if data is not None else virtual_path
                if suffix == ".gz":
                    raw_file = gzip.GzipFile(fileobj=src_file, mode="rb") if data is not None else gzip.open(src_file, "rb")
                elif suffix == ".bz2":
                    raw_file = bz2.BZ2File(src_file, mode="rb") if data is not None else bz2.open(src_file, "rb")
                else:
                    raw_file = lzma.LZMAFile(src_file, mode="rb") if data is not None else lzma.open(src_file, "rb")

                with raw_file:
                    decompressed_bytes = raw_file.read()

                parent_str = str(virtual_path)
                if parent_str.lower().endswith(suffix):
                    nested_virtual_path = Path(parent_str[:-len(suffix)])
                else:
                    nested_virtual_path = Path(f"{virtual_path}:decompressed")

                return process_file_recursive(
                    nested_virtual_path, config, seen, records, stats, data=decompressed_bytes
                )
            except Exception as e:
                print(f"pygrep: {virtual_path}: error leyendo archivo comprimido: {e}", file=sys.stderr)
                return False, True, 0, 0

    # Leaf node processing
    if data is not None:
        clean_path = get_clean_internal_path(virtual_path)
        if not file_matches_filter(clean_path, config.include_patterns, config.exclude_patterns):
            return False, False, 0, 0

        chunk = data[:8192]
        is_binary = b"\x00" in chunk

        if is_binary:
            has_match = bool(config.pattern.search(chunk.decode(config.encoding, errors="replace")))
            if not config.count_only:
                if config.files_with_matches and has_match:
                    safe_print(format_filename(virtual_path))
                elif config.files_without_matches and not has_match:
                    safe_print(format_filename(virtual_path))
                elif has_match:
                    safe_print(f"El archivo binario {virtual_path} coincide")
            return has_match, False, (1 if has_match else 0), 0
        else:
            raw_file = io.BytesIO(data)
            stream = io.TextIOWrapper(raw_file, encoding=config.encoding, errors="replace")
            try:
                match_count, line_count = process_stream(stream, virtual_path, config, seen, records, stats)
                has_match = match_count > 0
                if not config.count_only:
                    if config.files_with_matches and has_match:
                        safe_print(format_filename(virtual_path))
                    elif config.files_without_matches and not has_match:
                        safe_print(format_filename(virtual_path))
                return has_match, False, match_count, line_count
            except Exception as e:
                print(f"pygrep: {virtual_path}: error de decodificación: {e}", file=sys.stderr)
                return False, True, 0, 0
    else:
        # Standard filesystem file
        try:
            stream, is_binary, chunk = open_file_safely(virtual_path, config)
        except PermissionError:
            print(f"pygrep: {virtual_path}: Permiso denegado", file=sys.stderr)
            return False, True, 0, 0
        except LookupError as e:
            print(f"pygrep: {virtual_path}: codificación inválida: {e}", file=sys.stderr)
            return False, True, 0, 0
        except OSError as e:
            print(f"pygrep: {virtual_path}: {e}", file=sys.stderr)
            return False, True, 0, 0

        if is_binary:
            has_match = bool(config.pattern.search(chunk.decode(config.encoding, errors="replace")))
            if not config.count_only:
                if config.files_with_matches and has_match:
                    safe_print(format_filename(virtual_path))
                elif config.files_without_matches and not has_match:
                    safe_print(format_filename(virtual_path))
                elif has_match:
                    safe_print(f"El archivo binario {virtual_path} coincide")
            return has_match, False, (1 if has_match else 0), 0

        assert stream is not None

        # Optimización mmap para --multiline en archivos de texto regulares.
        # Se cierra el TextIOWrapper abierto por open_file_safely y se delega a
        # process_multiline_mmap, que mapea el archivo en memoria virtual y busca
        # directamente sobre los bytes sin decodificar el archivo completo.
        # Condiciones de activación:
        #   • --multiline activo
        #   • pattern_bytes compilado con éxito (fallback si el patrón no es encodable)
        #   • --auto-encoding desactivado (encoding fijo necesario para el patrón bytes)
        if (
            config.multiline
            and config.pattern_bytes is not None
            and not config.auto_encoding
        ):
            stream.close()
            try:
                from pygrep_core.engine import process_multiline_mmap
                match_count, line_count = process_multiline_mmap(
                    virtual_path, config, seen, records, stats
                )
                has_match = match_count > 0
                if not config.count_only:
                    if config.files_with_matches and has_match:
                        safe_print(format_filename(virtual_path))
                    elif config.files_without_matches and not has_match:
                        safe_print(format_filename(virtual_path))
                return has_match, False, match_count, line_count
            except OSError:
                # mmap no disponible (caso muy raro); reabrir en modo texto
                try:
                    stream, _, _ = open_file_safely(virtual_path, config)
                except OSError:
                    return False, True, 0, 0

        try:
            with stream:
                match_count, line_count = process_stream(stream, virtual_path, config, seen, records, stats)
                has_match = match_count > 0
                if not config.count_only:
                    if config.files_with_matches and has_match:
                         safe_print(format_filename(virtual_path))
                    elif config.files_without_matches and not has_match:
                         safe_print(format_filename(virtual_path))
                return has_match, False, match_count, line_count
        except UnicodeDecodeError as e:
            print(f"pygrep: {virtual_path}: error de decodificación: {e}", file=sys.stderr)
            return False, True, 0, 0


def process_file(
    path: Path,
    config: Config,
    seen: set[str] | None,
    records: list,
    stats=None,
) -> tuple[bool, bool, int, int]:
    """Procesa un archivo determinado por su ruta, delegando a subprocesadores según su tipo.
    
    Soporta archivos normales y archivos comprimidos o archivadores (ZIP, TAR, etc.)
    si la opción `search_zip` está activa. Retorna una tupla con (has_match, errored, match_count, line_count).
    """
    return process_file_recursive(path, config, seen, records, stats)
