from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ALLOWED_IMPORTS = {"pandas", "polars", "numpy", "scipy", "statsmodels", "sklearn", "plotly", "math", "statistics", "json"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "input", "breakpoint", "__import__"}
FORBIDDEN_ATTRIBUTES = {"system", "popen", "spawn", "fork", "remove", "unlink", "rmdir", "rmtree", "connect", "request", "urlopen"}


def validate_python(code: str) -> list[str]:
    issues: list[str] = []
    try: tree = ast.parse(code)
    except SyntaxError as error: return [f"Syntax error at line {error.lineno}: {error.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS: issues.append(f"Import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS: issues.append(f"Import is not allowed: {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS: issues.append(f"Call is not allowed: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTES: issues.append(f"Attribute call is not allowed: {node.func.attr}")
        elif isinstance(node, (ast.Global, ast.Nonlocal)): issues.append("Global/nonlocal statements are not allowed")
    return sorted(set(issues))


def execute_python(code: str, project_directory: str, timeout_seconds: int) -> dict[str, Any]:
    issues = validate_python(code)
    if issues: return {"ok": False, "issues": issues}
    root = Path(project_directory).resolve()
    if not root.is_dir(): raise ValueError("Project directory does not exist")
    wrapper = """import json\n_namespace = {}\n_safe = {'len': len, 'range': range, 'min': min, 'max': max, 'sum': sum, 'print': print, 'abs': abs, 'round': round, 'enumerate': enumerate, 'zip': zip, 'float': float, 'int': int, 'str': str, 'bool': bool, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple, '__import__': __import__}\nexec(compile(%r, '<analysis>', 'exec'), {'__builtins__': _safe}, _namespace)\nprint('AIDA_RESULT=' + json.dumps(_namespace.get('result'), default=str))\n""" % code
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=root / ".aida", encoding="utf-8", delete=False) as handle:
        handle.write(wrapper); script = Path(handle.name)
    env = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "PYTHONPATH"}}
    try:
        completed = subprocess.run([sys.executable, "-I", str(script)], cwd=root, env=env, capture_output=True, text=True, timeout=timeout_seconds, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        marker = next((line.removeprefix("AIDA_RESULT=") for line in completed.stdout.splitlines() if line.startswith("AIDA_RESULT=")), "null")
        return {"ok": completed.returncode == 0, "result": json.loads(marker), "stdout": completed.stdout, "stderr": completed.stderr, "exitCode": completed.returncode, "issues": []}
    except subprocess.TimeoutExpired: return {"ok": False, "issues": [f"Execution exceeded {timeout_seconds} seconds"]}
    finally: script.unlink(missing_ok=True)
