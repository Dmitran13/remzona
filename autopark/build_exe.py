import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "AutoPark"
ENTRY_POINT = "launcher.py"
BUILD_DIR = Path("build")
DIST_DIR = Path("dist")

def check_requirements():
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} найден")
    except ImportError:
        print("Установите: pip install pyinstaller==6.10.0")
        sys.exit(1)

def clean_build_dirs():
    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Очищена папка: {d}")

def ensure_data_dirs():
    for d in ["data/pdfs","data/chroma_db","credentials","static"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    print("Структура папок создана")

def build_exe():
    sep = ";" if sys.platform == "win32" else ":"
    hidden = [
        "chromadb","chromadb.api","chromadb.db.impl","chromadb.segment",
        "chromadb.utils.embedding_functions","sentence_transformers",
        "transformers","torch","fastapi","uvicorn","uvicorn.logging",
        "uvicorn.loops","uvicorn.loops.auto","uvicorn.protocols",
        "uvicorn.protocols.http","uvicorn.protocols.http.auto",
        "uvicorn.lifespan","uvicorn.lifespan.on","starlette",
        "starlette.staticfiles","multipart","gspread","google.auth",
        "google.oauth2.service_account","pdfplumber","pystray",
        "PIL","PIL.Image","PIL.ImageDraw","openai","dotenv",
    ]
    hidden_args = []
    for h in hidden: hidden_args += ["--hidden-import", h]

    add_data = [f"static{sep}static", f"data{sep}data"]
    if Path("credentials").exists():
        add_data.append(f"credentials{sep}credentials")
    add_data_args = []
    for d in add_data: add_data_args += ["--add-data", d]

    cmd = [sys.executable, "-m", "PyInstaller",
           "--onefile", "--windowed", "--name", APP_NAME,
           *add_data_args, *hidden_args,
           "--noupx", "--clean",
           "--collect-all", "chromadb",
           "--collect-all", "sentence_transformers",
           "--collect-all", "pdfplumber",
           ENTRY_POINT]

    print("Запускаем PyInstaller (5-15 минут)...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Ошибка сборки!")
        sys.exit(1)

def post_build():
    exe_name = APP_NAME + (".exe" if sys.platform == "win32" else "")
    exe_path = DIST_DIR / exe_name
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024*1024)
        print(f"\nСБОРКА ЗАВЕРШЕНА!\nФайл: {exe_path.absolute()}\nРазмер: {size_mb:.1f} МБ")
        return str(exe_path.absolute())
    else:
        print("Файл не найден после сборки")
        sys.exit(1)

def main():
    if not Path(ENTRY_POINT).exists():
        print(f"Запускайте из папки autopark/")
        sys.exit(1)
    check_requirements()
    clean_build_dirs()
    ensure_data_dirs()
    build_exe()
    post_build()

if __name__ == "__main__":
    main()
