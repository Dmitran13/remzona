import logging
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import Config, save_settings
from services import maintenance_logic, pdf_indexer, qwen_service
from services.sheets_reader import get_sheets_reader

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

app = FastAPI(title=Config.APP_NAME, version=Config.APP_VERSION, docs_url="/docs")

if Config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(Config.STATIC_DIR)), name="static")

class VehicleRequest(BaseModel):
    plate: str

class AskRequest(BaseModel):
    plate: str
    question: str

class PartsRequest(BaseModel):
    part_name: str
    car_model: str

class SettingsRequest(BaseModel):
    qwen_api_key: str
    google_sheet_id: str
    google_sheet_tab: str = "Sheet1"

@app.get("/")
async def root():
    index_path = Config.STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/status")
async def get_status():
    reader = get_sheets_reader()
    sheets_status = reader.get_status()
    pdf_stats = pdf_indexer.get_stats()
    return {"sheets_ok": sheets_status["connected"],
            "sheets_records": sheets_status["records_count"],
            "pdfs_count": pdf_stats["total_files"],
            "chunks_count": pdf_stats["total_chunks"],
            "cache_age_minutes": sheets_status["cache_age_minutes"],
            "version": Config.APP_VERSION,
            "configured": bool(Config.QWEN_API_KEY and Config.GOOGLE_SHEET_ID)}

@app.get("/api/plates")
async def get_plates():
    try:
        reader = get_sheets_reader()
        return {"plates": reader.get_all_plates()}
    except Exception as e:
        return {"plates": [], "error": str(e)}

@app.post("/api/vehicle")
async def get_vehicle_info(request: VehicleRequest):
    plate = request.plate.strip()
    if not plate:
        raise HTTPException(status_code=400, detail="Госномер не указан")
    reader = get_sheets_reader()
    history = reader.get_vehicle_history(plate)
    car_model = reader.get_car_model(plate)
    current_mileage = reader.get_current_mileage(plate)
    if not history:
        return {"plate": plate, "car_model": car_model or "Неизвестно",
                "current_mileage": current_mileage, "history_count": 0,
                "maintenance": [], "last_records": [], "anomalies": [],
                "message": "Записей не найдено. Проверьте госномер."}
    maintenance = maintenance_logic.analyze_maintenance_status(history, current_mileage)
    anomalies = maintenance_logic.get_anomalies(maintenance)
    last_records = [{"date": r.get("date",""), "mileage": r.get("mileage",""),
                     "work_type": r.get("work_type",""), "part": r.get("part",""),
                     "article": r.get("article",""), "master": r.get("master","")}
                    for r in history[:20]]
    return {"plate": plate, "car_model": car_model, "current_mileage": current_mileage,
            "history_count": len(history), "maintenance": maintenance,
            "last_records": last_records, "anomalies": [a["name"] for a in anomalies]}

@app.post("/api/ask")
async def ask_mechanic(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")
    reader = get_sheets_reader()
    car_model, current_mileage, history = "", None, []
    if request.plate:
        car_model = reader.get_car_model(request.plate)
        current_mileage = reader.get_current_mileage(request.plate)
        history = reader.get_vehicle_history(request.plate, limit=20)
    car_info = car_model or "Модель не указана"
    if current_mileage: car_info += f", пробег {current_mileage:,} км"
    manual_chunks = pdf_indexer.search_manuals(request.question, car_model=car_model, n_results=5)
    answer = qwen_service.ask_mechanic(request.question, manual_chunks, history, car_info)
    sources = []
    seen = set()
    for chunk in manual_chunks:
        key = f"{chunk['source']}_{chunk['page']}"
        if key not in seen and chunk.get("score",0) > 0.3:
            sources.append({"filename": chunk["source"], "page": chunk["page"], "score": chunk["score"]})
            seen.add(key)
    return {"answer": answer, "sources": sources[:3]}

@app.post("/api/parts")
async def search_parts(request: PartsRequest):
    if not request.part_name.strip():
        raise HTTPException(status_code=400, detail="Название запчасти не указано")
    return qwen_service.search_part_numbers(request.part_name, request.car_model)

@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Можно загружать только PDF файлы")
    save_path = Config.PDFS_DIR / file.filename
    try:
        with open(save_path, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения: {e}")
    result = pdf_indexer.index_pdf_file(str(save_path))
    if result["status"] == "error":
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Ошибка индексации: {result.get('error')}")
    return {"filename": result["filename"], "chunks": result["chunks_count"],
            "pages": result["pages_count"], "car_model": result.get("car_model",""),
            "status": result["status"]}

@app.delete("/api/pdf/{filename}")
async def delete_pdf(filename: str):
    pdf_indexer.delete_indexed_file(filename)
    file_path = Config.PDFS_DIR / filename
    if file_path.exists(): file_path.unlink()
    return {"status": "ok", "message": f"{filename} удалён"}

@app.get("/api/pdfs")
async def get_pdfs():
    indexed_files = {f["filename"]: f for f in pdf_indexer.get_indexed_files()}
    pdf_list = []
    for pdf_path in sorted(Config.PDFS_DIR.glob("*.pdf")):
        size_mb = round(pdf_path.stat().st_size / (1024*1024), 2)
        info = indexed_files.get(pdf_path.name, {})
        pdf_list.append({"filename": pdf_path.name, "size_mb": size_mb,
            "chunks": info.get("chunks",0), "indexed_at": info.get("indexed_at",""),
            "car_model": info.get("car_model",""), "is_indexed": pdf_path.name in indexed_files})
    return {"pdfs": pdf_list}

@app.post("/api/refresh")
async def refresh_cache():
    return get_sheets_reader().refresh_cache()

@app.post("/api/save-settings")
async def save_app_settings(request: SettingsRequest):
    try:
        save_settings(request.qwen_api_key, request.google_sheet_id, request.google_sheet_tab)
        reader = get_sheets_reader()
        reader._sheet = None
        reader._client = None
        return {"status": "ok", "message": "Настройки сохранены"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/check-qwen")
async def check_qwen():
    ok, message = qwen_service.check_api_key()
    return {"ok": ok, "message": message}

@app.post("/api/check-sheets")
async def check_sheets():
    ok, message = get_sheets_reader().check_connection()
    return {"ok": ok, "message": message}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=Config.APP_HOST, port=Config.APP_PORT, reload=True)
