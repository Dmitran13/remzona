import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

class Config:
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL_MAIN: str = "qwen-plus"
    QWEN_MODEL_FAST: str = "qwen-turbo"
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_SHEET_TAB: str = os.getenv("GOOGLE_SHEET_TAB", "Sheet1")
    GOOGLE_CREDENTIALS_PATH: Path = BASE_DIR / "credentials" / "google_service_account.json"
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    APP_HOST: str = "127.0.0.1"
    CACHE_TTL_MINUTES: int = int(os.getenv("CACHE_TTL_MINUTES", "5"))
    DATA_DIR: Path = BASE_DIR / "data"
    PDFS_DIR: Path = BASE_DIR / "data" / "pdfs"
    CHROMA_DIR: Path = BASE_DIR / "data" / "chroma_db"
    STATIC_DIR: Path = BASE_DIR / "static"
    APP_VERSION: str = "1.0.0"
    APP_NAME: str = "АвтоПарк — Помощник механика"

Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
Config.PDFS_DIR.mkdir(parents=True, exist_ok=True)
Config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

def is_configured() -> bool:
    return bool(Config.QWEN_API_KEY and Config.GOOGLE_SHEET_ID)

def save_settings(qwen_api_key: str, google_sheet_id: str, google_sheet_tab: str) -> None:
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    settings = {
        "QWEN_API_KEY": qwen_api_key,
        "GOOGLE_SHEET_ID": google_sheet_id,
        "GOOGLE_SHEET_TAB": google_sheet_tab,
    }
    existing_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=")[0].strip()
            if key in settings:
                new_lines.append(f"{key}={settings[key]}\n")
                existing_keys.add(key)
                continue
        new_lines.append(line)
    for key, value in settings.items():
        if key not in existing_keys:
            new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    load_dotenv(env_path, override=True)
    Config.QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
    Config.GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
    Config.GOOGLE_SHEET_TAB = os.getenv("GOOGLE_SHEET_TAB", "Sheet1")
