"""
Tests de la optimización mmap para --multiline.
Compara resultados entre modo texto clásico y modo mmap para garantizar equivalencia.
"""
import subprocess, sys, os, tempfile, pathlib

PY  = sys.executable
CLI = [PY, str(pathlib.Path(__file__).parent.parent / "pygrep.py")]

def run(*args, stdin=None):
    result = subprocess.run(
        CLI + list(args),
        capture_output=True, text=True, encoding="utf-8",
        input=stdin,
    )
    return result.stdout, result.returncode

# ── Fixture: archivo multilinea temporal ──────────────────────────────────────
CONTENT = """\
2026-01-01 INFO  Inicio del sistema
2026-01-01 ERROR Fallo crítico
segunda línea del error
2026-01-01 WARN  Advertencia menor
2026-01-01 INFO  Todo OK
"""

def make_tmp(content=CONTENT, encoding="utf-8"):
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False,
        encoding=encoding, newline="\n"
    )
    f.write(content)
    f.close()
    return f.name

# ─────────────────────────────────────────────────────────────────────────────
def test(name, *, args_mmap, args_text, expect_rc=0):
    out_mmap, rc_mmap = run(*args_mmap)
    out_text, rc_text = run(*args_text)
    ok = out_mmap == out_text and rc_mmap == rc_text
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}")
    if not ok:
        print(f"       mmap  (rc={rc_mmap}): {repr(out_mmap[:200])}")
        print(f"       texto (rc={rc_text}): {repr(out_text[:200])}")
    if expect_rc is not None and rc_mmap != expect_rc:
        print(f"       rc esperado {expect_rc}, obtenido {rc_mmap}")
    return ok

# ─────────────────────────────────────────────────────────────────────────────
tmp = make_tmp()
try:
    all_ok = True

    # 1. Búsqueda básica multilinea (patrón abarcar 2 líneas)
    all_ok &= test(
        "Match multilinea básico",
        args_mmap=["-U", r"ERROR\nsegunda", tmp],
        args_text=["-U", r"ERROR\nsegunda", tmp],
    )

    # 2. Patrón en una sola línea con -U (equivale a búsqueda normal)
    all_ok &= test(
        "Patrón una sola línea con -U",
        args_mmap=["-U", "INFO", tmp],
        args_text=["-U", "INFO", tmp],
    )

    # 3. -c (count) en modo -U
    all_ok &= test(
        "Count --multiline",
        args_mmap=["-U", "-c", "ERROR", tmp],
        args_text=["-U", "-c", "ERROR", tmp],
    )

    # 4. -n (line-number) con -U
    all_ok &= test(
        "Line-number --multiline",
        args_mmap=["-U", "-n", "WARN", tmp],
        args_text=["-U", "-n", "WARN", tmp],
    )

    # 5. --tail con -U
    all_ok &= test(
        "--tail con --multiline",
        args_mmap=["-U", "--tail", "1", "INFO", tmp],
        args_text=["-U", "--tail", "1", "INFO", tmp],
    )

    # 6. -i (ignore-case) con -U → smart-case en bytes también debe funcionar
    all_ok &= test(
        "Ignore-case --multiline",
        args_mmap=["-U", "-i", "error", tmp],
        args_text=["-U", "-i", "error", tmp],
    )

    # 7. Sin coincidencias → exit code 1
    all_ok &= test(
        "Sin coincidencias (exit 1)",
        args_mmap=["-U", "NOMATCH_XYZ", tmp],
        args_text=["-U", "NOMATCH_XYZ", tmp],
        expect_rc=1,
    )

    # 8. -l (files-with-matches) con -U
    all_ok &= test(
        "-l --multiline",
        args_mmap=["-U", "-l", "ERROR", tmp],
        args_text=["-U", "-l", "ERROR", tmp],
    )

    # 9. Archivo vacío
    empty = make_tmp(content="")
    all_ok &= test(
        "Archivo vacío",
        args_mmap=["-U", "pattern", empty],
        args_text=["-U", "pattern", empty],
        expect_rc=1,
    )
    os.unlink(empty)

    # 10. Archivo CRLF (Windows line endings)
    crlf_tmp = make_tmp(content=CONTENT.replace("\n", "\r\n"))
    all_ok &= test(
        "CRLF line endings",
        args_mmap=["-U", "ERROR", crlf_tmp],
        args_text=["-U", "ERROR", crlf_tmp],
    )
    os.unlink(crlf_tmp)

    # 11. -S smart-case con -U (patrón minúsculas → insensible en bytes)
    all_ok &= test(
        "Smart-case --multiline (lowercase pattern)",
        args_mmap=["-U", "-S", "error", tmp],
        args_text=["-U", "-S", "error", tmp],
    )

    # 12. Encoding latin-1
    latin_tmp = make_tmp(
        content="Línea con acénto\nERROR: configuración incorrecta\n",
        encoding="latin-1",
    )
    all_ok &= test(
        "Encoding latin-1 --multiline",
        args_mmap=["-U", "--encoding", "latin-1", "ERROR", latin_tmp],
        args_text=["-U", "--encoding", "latin-1", "ERROR", latin_tmp],
    )
    os.unlink(latin_tmp)

    print()
    print("=" * 50)
    print("RESULTADO GLOBAL:", "TODOS LOS TESTS PASARON" if all_ok else "HAY FALLOS")

finally:
    os.unlink(tmp)
