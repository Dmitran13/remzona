import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import chromadb
import pdfplumber
from chromadb.utils import embedding_functions
from config import Config

logger = logging.getLogger(__name__)
COLLECTION_NAME = "manuals"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

def _get_collection():
    client = chromadb.PersistentClient(path=str(Config.CHROMA_DIR))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-mpnet-base-v2")
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn,
                                           metadata={"hnsw:space": "cosine"})

def _extract_car_model_from_filename(filename):
    name = Path(filename).stem.lower()
    parts = re.split(r"[_\-\s]+", name)
    brand_map = {
        "toyota": "Toyota", "camry": "Toyota Camry", "corolla": "Toyota Corolla",
        "rav4": "Toyota RAV4", "honda": "Honda", "civic": "Honda Civic",
        "accord": "Honda Accord", "nissan": "Nissan", "qashqai": "Nissan Qashqai",
        "kia": "Kia", "rio": "Kia Rio", "sportage": "Kia Sportage", "ceed": "Kia Ceed",
        "hyundai": "Hyundai", "solaris": "Hyundai Solaris", "tucson": "Hyundai Tucson",
        "lada": "Lada", "vesta": "Lada Vesta", "granta": "Lada Granta",
        "volkswagen": "Volkswagen", "vw": "Volkswagen", "polo": "Volkswagen Polo",
        "bmw": "BMW", "mercedes": "Mercedes-Benz", "audi": "Audi",
        "renault": "Renault", "logan": "Renault Logan", "duster": "Renault Duster",
        "skoda": "Skoda", "octavia": "Skoda Octavia", "ford": "Ford",
        "focus": "Ford Focus", "mazda": "Mazda", "mitsubishi": "Mitsubishi",
    }
    result_parts = []
    for part in parts:
        if re.match(r"^\d{4}$", part): result_parts.append(part)
        elif part in brand_map: result_parts.append(brand_map[part])
        else: result_parts.append(part.capitalize())
    seen, unique = set(), []
    for p in result_parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return " ".join(unique) if unique else Path(filename).stem

def _split_text_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if not text or len(text) < chunk_size // 2: return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk: chunks.append(chunk)
            break
        cut_pos = end
        for sep in [". ", ".\n", "! ", "\n\n", "\n"]:
            pos = text.rfind(sep, start + chunk_size // 2, end)
            if pos != -1:
                cut_pos = pos + len(sep)
                break
        chunk = text[start:cut_pos].strip()
        if chunk: chunks.append(chunk)
        start = cut_pos - overlap
    return chunks

def index_pdf_file(filepath):
    path = Path(filepath)
    filename = path.name
    try:
        collection = _get_collection()
        car_model = _extract_car_model_from_filename(filename)
        indexed_at = datetime.now().isoformat()
        all_chunks, all_ids, all_metadatas = [], [], []
        pages_count = 0
        with pdfplumber.open(filepath) as pdf:
            pages_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                if not page_text: continue
                for chunk_idx, chunk_text in enumerate(_split_text_into_chunks(page_text)):
                    all_chunks.append(chunk_text)
                    all_ids.append(f"{filename}__p{page_num}__c{chunk_idx}")
                    all_metadatas.append({"source": filename, "filename": filename,
                        "page": page_num, "car_model": car_model,
                        "indexed_at": indexed_at, "chunk_index": chunk_idx})
        if not all_chunks:
            return {"filename": filename, "chunks_count": 0, "pages_count": pages_count,
                    "status": "empty", "error": "Не удалось извлечь текст"}
        for i in range(0, len(all_chunks), 100):
            collection.upsert(documents=all_chunks[i:i+100], ids=all_ids[i:i+100],
                              metadatas=all_metadatas[i:i+100])
        return {"filename": filename, "chunks_count": len(all_chunks),
                "pages_count": pages_count, "car_model": car_model, "status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка индексации {filename}: {e}")
        return {"filename": filename, "chunks_count": 0, "pages_count": 0,
                "status": "error", "error": str(e)}

def index_all_pdfs():
    already_indexed = {f["filename"] for f in get_indexed_files()}
    results = []
    for pdf_path in Config.PDFS_DIR.glob("*.pdf"):
        if pdf_path.name not in already_indexed:
            results.append(index_pdf_file(str(pdf_path)))
    return results

def get_indexed_files():
    try:
        collection = _get_collection()
        result = collection.get(include=["metadatas"])
        if not result or not result["metadatas"]: return []
        files_info = {}
        for meta in result["metadatas"]:
            fname = meta.get("filename", "unknown")
            if fname not in files_info:
                files_info[fname] = {"filename": fname, "chunks": 0,
                    "indexed_at": meta.get("indexed_at",""), "car_model": meta.get("car_model","")}
            files_info[fname]["chunks"] += 1
        return list(files_info.values())
    except Exception as e:
        logger.error(f"Ошибка получения файлов: {e}")
        return []

def delete_indexed_file(filename):
    try:
        collection = _get_collection()
        result = collection.get(where={"filename": filename}, include=["metadatas"])
        if not result["ids"]: return False
        collection.delete(ids=result["ids"])
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления {filename}: {e}")
        return False

def search_manuals(query, car_model=None, n_results=5):
    try:
        collection = _get_collection()
        if collection.count() == 0: return []
        where_filter = None
        if car_model and car_model.strip():
            where_filter = {"car_model": {"$contains": car_model.split()[0]}}
        results = collection.query(query_texts=[query],
            n_results=min(n_results, collection.count()),
            where=where_filter, include=["documents","metadatas","distances"])
        found = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(results["documents"][0],
                                       results["metadatas"][0], results["distances"][0]):
                found.append({"text": doc, "source": meta.get("source",""),
                    "page": meta.get("page",0), "car_model": meta.get("car_model",""),
                    "score": round(1 - dist/2, 3)})
        return found
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return []

def get_stats():
    try:
        collection = _get_collection()
        return {"total_files": len(get_indexed_files()), "total_chunks": collection.count()}
    except Exception as e:
        return {"total_files": 0, "total_chunks": 0}
