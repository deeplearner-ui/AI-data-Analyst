"""Build a portable Windows sidecar runtime for electron-builder."""
from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parent
PyInstaller.__main__.run([
    str(ROOT / "launcher.py"),
    "--name=aida-sidecar",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--console",
    f"--distpath={ROOT / 'dist'}",
    f"--workpath={ROOT / 'build' / 'pyinstaller'}",
    f"--specpath={ROOT / 'build'}",
    "--collect-submodules=sqlalchemy.dialects",
    "--hidden-import=psycopg",
    "--hidden-import=pymysql",
    "--hidden-import=pyarrow",
    "--hidden-import=openpyxl",
    "--hidden-import=reportlab.platypus",
    "--hidden-import=reportlab.pdfbase.ttfonts",
    "--collect-submodules=aida_sidecar",
])
