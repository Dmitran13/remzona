import logging
import re
from datetime import datetime, timedelta
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials
from config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]

COLUMN_ALIASES = {
    "date":      ["дата", "date", "дата работы", "дата ремонта"],
    "plate":     ["госномер", "номер", "гос. номер", "гос номер", "plate"],
    "model":     ["модель", "марка", "автомобиль", "авто", "model"],
    "mileage":   ["пробег", "км", "mileage", "одометр"],
    "work_type": ["вид работы", "работа", "услуга", "тип работы", "work"],
    "part":      ["запчасть", "деталь", "part", "запч"],
    "article":   ["артикул", "арт", "art", "article", "код"],
    "master":    ["мастер", "механик", "master"],
    "notes":     ["примечание", "примечания", "заметки", "notes"],
}

def _normalize_plate(plate):
    if not plate: return ""
    return re.sub(r"[\s\-_]", "", plate.upper().strip())

def _parse_date(date_str):
    if not date_str: return None
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%d-%m-%Y"]:
        try: return datetime.strptime(date_str.strip(), fmt)
        except ValueError: continue
    return None

def _safe_int(value):
    if not value: return None
    cleaned = re.sub(r"[^\d]", "", str(value))
    return int(cleaned) if cleaned else None

class SheetsReader:
    def __init__(self):
        self._cache = []
        self._cache_time = None
        self._column_map = {}
        self._client = None
        self._sheet = None
        self._is_connected = False
        self._last_error = ""

    def _get_client(self):
        if self._client: return self._client
        creds_path = Config.GOOGLE_CREDENTIALS_PATH
        if not creds_path.exists():
            raise FileNotFoundError(f"Файл не найден: {creds_path}")
        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        self._client = gspread.authorize(creds)
        return self._client

    def _get_sheet(self):
        if self._sheet: return self._sheet
        client = self._get_client()
        spreadsheet = client.open_by_key(Config.GOOGLE_SHEET_ID)
        self._sheet = spreadsheet.worksheet(Config.GOOGLE_SHEET_TAB)
        return self._sheet

    def _detect_columns(self, header_row):
        column_map = {}
        for logical_name, aliases in COLUMN_ALIASES.items():
            for col_idx, header in enumerate(header_row):
                if header.lower().strip() in aliases:
                    column_map[logical_name] = col_idx
                    break
        return column_map

    def _row_to_dict(self, row):
        result = {}
        for logical_name, col_idx in self._column_map.items():
            result[logical_name] = row[col_idx].strip() if col_idx < len(row) and row[col_idx] else ""
        if "date" in result and result["date"]:
            parsed = _parse_date(result["date"])
            result["date_obj"] = parsed
            if parsed: result["date"] = parsed.strftime("%d.%m.%Y")
        if "mileage" in result: result["mileage_int"] = _safe_int(result["mileage"])
        if "plate" in result: result["plate_normalized"] = _normalize_plate(result["plate"])
        return result

    def _is_cache_valid(self):
        if not self._cache or not self._cache_time: return False
        return datetime.now() - self._cache_time < timedelta(minutes=Config.CACHE_TTL_MINUTES)

    def _load_all_data(self):
        try:
            sheet = self._get_sheet()
            all_values = sheet.get_all_values()
            if not all_values:
                self._cache = []
                self._cache_time = datetime.now()
                self._is_connected = True
                return
            header_row = all_values[0]
            self._column_map = self._detect_columns(header_row)
            if not self._column_map:
                default = ["date","plate","model","mileage","work_type","part","article","master","notes"]
                self._column_map = {name: idx for idx, name in enumerate(default)}
            records = []
            for row in all_values[1:]:
                if any(cell.strip() for cell in row):
                    records.append(self._row_to_dict(row))
            self._cache = records
            self._cache_time = datetime.now()
            self._is_connected = True
            self._last_error = ""
            logger.info(f"Загружено: {len(records)} записей")
        except Exception as e:
            self._is_connected = False
            self._last_error = str(e)
            logger.error(f"Ошибка загрузки: {e}")
            if not self._cache: raise

    def _ensure_data(self):
        if not self._is_cache_valid(): self._load_all_data()

    def get_vehicle_history(self, plate, limit=100):
        self._ensure_data()
        normalized = _normalize_plate(plate)
        if not normalized: return []
        history = [r for r in self._cache if _normalize_plate(r.get("plate","")) == normalized]
        history.sort(key=lambda r: r.get("date_obj") or datetime.min, reverse=True)
        return history[:limit]

    def get_all_plates(self):
        self._ensure_data()
        plates = set()
        for record in self._cache:
            plate = record.get("plate","").strip()
            if plate: plates.add(plate.upper())
        return sorted(plates)

    def get_current_mileage(self, plate):
        history = self.get_vehicle_history(plate)
        max_mileage = None
        for record in history:
            mileage = record.get("mileage_int")
            if mileage and (max_mileage is None or mileage > max_mileage):
                max_mileage = mileage
        return max_mileage

    def get_car_model(self, plate):
        history = self.get_vehicle_history(plate, limit=1)
        return history[0].get("model","").strip() if history else ""

    def refresh_cache(self):
        self._cache = []
        self._cache_time = None
        self._sheet = None
        try:
            self._load_all_data()
            return {"records_count": len(self._cache),
                    "updated_at": self._cache_time.strftime("%d.%m.%Y %H:%M") if self._cache_time else "",
                    "status": "ok"}
        except Exception as e:
            return {"records_count": 0, "updated_at": "", "status": "error", "error": str(e)}

    def get_status(self):
        age_minutes = None
        if self._cache_time:
            age_minutes = round((datetime.now() - self._cache_time).total_seconds() / 60, 1)
        return {"connected": self._is_connected, "records_count": len(self._cache),
                "cache_age_minutes": age_minutes, "last_error": self._last_error}

    def check_connection(self):
        try:
            sheet = self._get_sheet()
            first_row = sheet.row_values(1)
            return True, f"Подключено. Найдено колонок: {len(first_row)}"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"

_reader_instance = None

def get_sheets_reader() -> SheetsReader:
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = SheetsReader()
    return _reader_instance
