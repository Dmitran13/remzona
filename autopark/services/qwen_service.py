import json
import logging
from typing import Optional
from openai import OpenAI
from config import Config

logger = logging.getLogger(__name__)

def _get_client() -> OpenAI:
    return OpenAI(api_key=Config.QWEN_API_KEY, base_url=Config.QWEN_BASE_URL)

def ask_mechanic(question: str, manual_chunks: list, history: list, car_info: str) -> str:
    client = _get_client()
    context_parts = []
    if manual_chunks:
        context_parts.append("=== ВЫДЕРЖКИ ИЗ МАНУАЛОВ ===")
        for chunk in manual_chunks[:5]:
            source_info = f"[{chunk.get('source','?')}, стр.{chunk.get('page','?')}]"
            context_parts.append(f"{source_info}\n{chunk.get('text','')}")
    if history:
        context_parts.append("\n=== ИСТОРИЯ ОБСЛУЖИВАНИЯ ===")
        for record in history[:10]:
            line = f"• {record.get('date','?')} | {record.get('mileage','?')} км | {record.get('work_type','?')}"
            if record.get('part'): line += f" | {record.get('part')}"
            if record.get('article'): line += f" | арт. {record.get('article')}"
            context_parts.append(line)
    context_text = "\n".join(context_parts) if context_parts else "Контекст недоступен."
    system_prompt = (f"Ты опытный автомеханик. Отвечай кратко и по делу на русском языке. "
                     f"Если в контексте есть артикулы деталей — обязательно укажи их. "
                     f"Давай практические советы. Автомобиль: {car_info}")
    user_prompt = f"{context_text}\n\n=== ВОПРОС ===\n{question}"
    try:
        response = client.chat.completions.create(
            model=Config.QWEN_MODEL_MAIN,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            max_tokens=1500, temperature=0.7)
        return response.choices[0].message.content or "Не удалось получить ответ."
    except Exception as e:
        logger.error(f"Ошибка ask_mechanic: {e}")
        return f"Ошибка подключения к AI: {str(e)}"

def search_part_numbers(part_name: str, car_model: str, year: str = "") -> dict:
    client = _get_client()
    car_desc = f"{car_model} {year}".strip()
    prompt = f"""Найди артикулы запчасти "{part_name}" для автомобиля {car_desc}.
Ответь СТРОГО в формате JSON (без markdown, только JSON):
{{"oem": ["OEM_артикул_1"], "analogues": [{{"brand": "NGK", "article": "BKR6E", "note": "аналог"}}], "search_tips": "подсказка"}}"""
    try:
        response = client.chat.completions.create(
            model=Config.QWEN_MODEL_FAST,
            messages=[{"role": "system", "content": "Ты эксперт по запчастям. Отвечай только валидным JSON."},
                      {"role": "user", "content": prompt}],
            max_tokens=800, temperature=0.3)
        raw = response.choices[0].message.content or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        result = json.loads(raw)
        if "oem" not in result: result["oem"] = []
        if "analogues" not in result: result["analogues"] = []
        if "search_tips" not in result: result["search_tips"] = ""
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        return {"oem": [], "analogues": [], "search_tips": "", "error": "Не удалось разобрать ответ AI"}
    except Exception as e:
        logger.error(f"Ошибка search_part_numbers: {e}")
        return {"oem": [], "analogues": [], "search_tips": "", "error": str(e)}

def analyze_anomaly(part_name: str, last_replaced_km: Optional[int],
                    recommended_km: Optional[int], current_km: int) -> str:
    client = _get_client()
    if last_replaced_km is not None:
        km_since = current_km - last_replaced_km
        situation = (f"Деталь '{part_name}': последняя замена на пробеге {last_replaced_km:,} км. "
                     f"Текущий пробег {current_km:,} км (прошло {km_since:,} км). ")
    else:
        situation = (f"Деталь '{part_name}': в истории нет записей о замене. "
                     f"Текущий пробег {current_km:,} км. ")
    if recommended_km:
        situation += f"Рекомендуемый интервал: {recommended_km:,} км."
    try:
        response = client.chat.completions.create(
            model=Config.QWEN_MODEL_FAST,
            messages=[{"role": "system", "content": "Ты опытный автомеханик. Краткие советы на русском."},
                      {"role": "user", "content": situation + "\nДай краткую рекомендацию (1-3 предложения)."}],
            max_tokens=300, temperature=0.7)
        return response.choices[0].message.content or "Требуется осмотр."
    except Exception as e:
        return "Рекомендуем проверить состояние детали при следующем ТО."

def check_api_key() -> tuple:
    if not Config.QWEN_API_KEY:
        return False, "API ключ не задан"
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=Config.QWEN_MODEL_FAST,
            messages=[{"role": "user", "content": "Скажи OK"}],
            max_tokens=10)
        return True, f"Соединение успешно: {response.choices[0].message.content.strip()}"
    except Exception as e:
        return False, f"Ошибка: {str(e)}"
