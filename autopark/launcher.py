import os
import sys
import threading
import time
import webbrowser
import logging
from pathlib import Path

log_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(str(log_dir / "autopark.log"), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def check_first_run():
    env_path = get_app_dir() / ".env"
    if not env_path.exists(): return True
    content = env_path.read_text(encoding="utf-8")
    has_qwen = any(l.startswith("QWEN_API_KEY=") and l.split("=",1)[1].strip()
                   for l in content.splitlines())
    return not has_qwen

def start_server():
    import uvicorn
    app_dir = get_app_dir()
    os.chdir(str(app_dir))
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    uvicorn.run("main:app", host="127.0.0.1", port=8000,
                log_level="warning", access_log=False)

def create_tray_icon(server_url):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("pystray или Pillow не установлены")
        return
    img = Image.new("RGBA", (64, 64), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0,0,63,63], fill=(26,26,46,255))
    draw.ellipse([4,4,59,59], fill=(233,69,96,255))
    draw.text((18,18), "А", fill=(255,255,255,255))

    def on_open(icon, item): webbrowser.open(server_url)
    def on_quit(icon, item):
        logger.info("Завершение")
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Открыть АвтоПарк", on_open, default=True),
        pystray.MenuItem("Выход", on_quit))
    icon = pystray.Icon("АвтоПарк", img, "АвтоПарк — Помощник механика", menu)
    icon.run()

def show_first_run_notice():
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("АвтоПарк — Первый запуск",
            "Добро пожаловать в АвтоПарк!\n\n"
            "Для начала работы:\n"
            "1. Перейти на вкладку НАСТРОЙКИ\n"
            "2. Ввести Qwen API ключ\n"
            "3. Ввести ID Google таблицы\n\n"
            "Нажмите OK чтобы открыть приложение.")
        root.destroy()
    except Exception as e:
        logger.warning(f"Диалог недоступен: {e}")

def main():
    logger.info("АвтоПарк запускается")
    app_dir = get_app_dir()
    os.chdir(str(app_dir))
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    server_url = "http://localhost:8000"
    is_first_run = check_first_run()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    logger.info("Сервер запущен")
    time.sleep(3)

    import urllib.request
    for attempt in range(5):
        try:
            urllib.request.urlopen(f"{server_url}/api/status", timeout=2)
            logger.info("Сервер готов")
            break
        except:
            time.sleep(1)

    if is_first_run:
        t = threading.Thread(target=show_first_run_notice, daemon=True)
        t.start()
        t.join(timeout=30)

    webbrowser.open(server_url)

    try:
        create_tray_icon(server_url)
    except Exception as e:
        logger.warning(f"Трей недоступен: {e}")
        server_thread.join()

if __name__ == "__main__":
    main()
