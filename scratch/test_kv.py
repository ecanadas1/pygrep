"""Script de prueba para las opciones --kv / --kv-filter / --kv-skip."""
import tempfile, os, sys

BASEDIR = os.path.dirname(os.path.abspath(__file__))
PYGREP  = os.path.join(BASEDIR, "pygrep.py")

LINES = [
    'ts=2026-06-01T10:00:00 level=error status=500 msg="disk full" host=web01\n',
    'ts=2026-06-01T10:01:00 level=info  status=200 msg="OK"         host=web01\n',
    'ts=2026-06-01T10:02:00 level=error status=503 msg="timeout"    host=web02\n',
    'ts=2026-06-01T10:03:00 level=warn  status=429 msg="rate limit" host=web01\n',
    'Esta linea NO tiene formato KV\n',
    'ts=2026-06-01T10:04:00 level=error status=502 msg="bad gateway" host=web02\n',
    'serial_number => 10012357, process_name => \'psr2\', log_category => \'AUDIT\'\n',
    'serial_number => 10012358, process_name => \'psr3\', log_category => \'OPERATIONS\'\n',
]

tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8')
tmp.writelines(LINES)
tmp.close()
F = tmp.name

def run(desc, args):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    cmd = f'python "{PYGREP}" {args} "{F}"'
    ret = os.system(cmd)
    print(f"  [exit: {ret}]")

run("TEST 1: --kv-filter level:error",
    '. --kv-filter "level:error"')

run("TEST 2: --kv-filter status:5xx  (wildcard x->\\d)",
    '. --kv-filter "status:5xx"')

run("TEST 3: --kv-filter level:error,host:web02  (multi-filtro)",
    '. --kv-filter "level:error,host:web02"')

run("TEST 4: --kv --kv-skip  (omitir lineas sin pares KV)",
    '. --kv --kv-skip')

run("TEST 5: sin --kv, busca 'error' (comportamiento inalterado)",
    '"error"')

run("TEST 6: incompatibilidad --kv + --multiline",
    '. --kv -U')

run("TEST 7: operador flecha '=>' con --kv-filter (ejemplo del equipo real)",
    '. --kv-filter "process_name:psr2,log_category:audit"')

os.unlink(tmp.name)
print("\nTodos los tests completados.\n")
