import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

MAINTENANCE_INTERVALS = {
    "Моторное масло":        {"km": 10000, "months": 12,  "keywords": ["масло", "моторное масло", "oil"]},
    "Масляный фильтр":       {"km": 10000, "months": 12,  "keywords": ["масляный фильтр", "oil filter"]},
    "Воздушный фильтр":      {"km": 20000, "months": 24,  "keywords": ["воздушный фильтр", "air filter"]},
    "Салонный фильтр":       {"km": 15000, "months": 12,  "keywords": ["салонный фильтр", "cabin filter"]},
    "Свечи зажигания":       {"km": 30000, "months": 36,  "keywords": ["свечи", "spark plug"]},
    "Передние колодки":      {"km": 30000, "months": None, "keywords": ["колодки передние", "передние колодки"]},
    "Задние колодки":        {"km": 50000, "months": None, "keywords": ["колодки задние", "задние колодки"]},
    "Тормозная жидкость":    {"km": None,  "months": 24,  "keywords": ["тормозная жидкость", "brake fluid"]},
    "Антифриз/Охлаждайка":   {"km": None,  "months": 36,  "keywords": ["антифриз", "охлаждающая жидкость"]},
    "Ремень ГРМ":            {"km": 90000, "months": 60,  "keywords": ["ремень грм", "грм", "timing belt"]},
    "Помпа":                 {"km": 90000, "months": 60,  "keywords": ["помпа", "водяной насос"]},
    "Ремень генератора":     {"km": 60000, "months": 48,  "keywords": ["ремень генератора", "alternator belt"]},
    "Свечи накала (дизель)": {"km": 60000, "months": None, "keywords": ["свечи накала", "glow plug"]},
    "АКПП масло":            {"km": 60000, "months": 48,  "keywords": ["масло акпп", "трансмиссионное масло"]},
    "Фильтр АКПП":           {"km": 60000, "months": 48,  "keywords": ["фильтр акпп", "atf filter"]},
}

WARNING_THRESHOLD = 0.15

def _find_last_maintenance(service_name, history):
    keywords = MAINTENANCE_INTERVALS.get(service_name, {}).get("keywords", [])
    last_km, last_date = None, None
    for record in history:
        combined = f"{record.get('work_type','').lower()} {record.get('part','').lower()}"
        for kw in keywords:
            if kw.lower() in combined:
                km = record.get("mileage_int")
                dt = record.get("date_obj")
                if km and (last_km is None or km > last_km):
                    last_km, last_date = km, dt
                elif dt and (last_date is None or dt > last_date):
                    if not km: last_date = dt
                break
    return last_km, last_date

def _calculate_km_status(last_km, interval_km, current_km):
    if interval_km is None or last_km is None: return None, None
    km_since = current_km - last_km
    return km_since, interval_km - km_since

def _calculate_date_status(last_date, interval_months):
    if interval_months is None or last_date is None: return None
    next_date = last_date + timedelta(days=interval_months * 30.44)
    return (next_date - datetime.now()).days

def _determine_status(km_until, interval_km, days_until, interval_months, has_data):
    if not has_data: return "unknown"
    if km_until is not None and interval_km:
        warn_km = int(interval_km * WARNING_THRESHOLD)
        if km_until < 0: return "overdue"
        if km_until <= warn_km: return "warning"
    if days_until is not None and interval_months:
        warn_days = int(interval_months * 30.44 * WARNING_THRESHOLD)
        if days_until < 0: return "overdue"
        if days_until <= warn_days: return "warning"
    if km_until is not None or days_until is not None: return "ok"
    return "unknown"

def _build_warning_message(name, status, last_km, last_date, km_until, days_until, current_km):
    if status == "unknown": return f"Нет данных о замене «{name}»"
    parts = []
    if status == "overdue":
        parts.append("⚠️ ПРОСРОЧЕНО:")
        if km_until is not None and km_until < 0: parts.append(f"просрочено на {abs(km_until):,} км")
        if days_until is not None and days_until < 0: parts.append(f"просрочено на {abs(days_until)} дней")
    elif status == "warning":
        parts.append("⏰ Скоро замена:")
        if km_until is not None and km_until >= 0: parts.append(f"осталось {km_until:,} км")
        if days_until is not None and days_until >= 0: parts.append(f"осталось {days_until} дней")
    elif status == "ok":
        if km_until is not None: parts.append(f"До следующей замены: {km_until:,} км")
        if days_until is not None: parts.append(f"{days_until} дней")
    if last_km:
        parts.append(f"(Последний раз: {last_km:,} км")
        parts.append(f"| {last_date.strftime('%d.%m.%Y')})" if last_date else ")")
    return " ".join(parts) if parts else name

def analyze_maintenance_status(history, current_mileage):
    results = []
    current_km = current_mileage or 0
    for name, intervals in MAINTENANCE_INTERVALS.items():
        interval_km = intervals.get("km")
        interval_months = intervals.get("months")
        last_km, last_date = _find_last_maintenance(name, history)
        has_data = last_km is not None or last_date is not None
        km_since, km_until = None, None
        if current_km and has_data:
            km_since, km_until = _calculate_km_status(last_km, interval_km, current_km)
        days_until = _calculate_date_status(last_date, interval_months)
        status = _determine_status(km_until, interval_km, days_until, interval_months, has_data)
        msg = _build_warning_message(name, status, last_km, last_date, km_until, days_until, current_km)
        results.append({"name": name, "status": status, "last_done_km": last_km,
            "last_done_date": last_date.strftime("%d.%m.%Y") if last_date else None,
            "km_since_last": km_since, "km_until_next": km_until,
            "days_until_next": days_until, "interval_km": interval_km,
            "interval_months": interval_months, "warning_message": msg})
    order = {"overdue": 0, "warning": 1, "ok": 2, "unknown": 3}
    results.sort(key=lambda x: order.get(x["status"], 4))
    return results

def get_anomalies(maintenance_list):
    return [i for i in maintenance_list if i["status"] in ("overdue", "warning")]
