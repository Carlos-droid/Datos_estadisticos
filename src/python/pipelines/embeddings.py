#!/usr/bin/env python3
"""Genera embeddings semánticos para catalog.jsonl usando Ollama.

Salida:
  processed/embeddings.npy      → Matriz numpy (N x 768)
  processed/embedding_ids.json  → Lista de IDs en el mismo orden
  processed/embedding_titles.json → Títulos para mostrar resultados
"""
import json, sys, time
from pathlib import Path

# Config portable
_this_dir = Path(__file__).resolve().parent
_repo_root = _this_dir.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.python.config import BASE_DIR
from src.python.log_utils import ScrapeLogger

log = ScrapeLogger("embeddings", "EMBED")

CATALOG_PATH = BASE_DIR / "processed" / "catalog.jsonl"
EMBED_DIR = BASE_DIR / "processed"
MODEL = "nomic-embed-text-v2-moe"
BATCH_SIZE = 10
SLEEP_BETWEEN = 0.2

def _get_embedding(text: str) -> list[float]:
    """Llama a Ollama para obtener un embedding."""
    import urllib.request
    payload = json.dumps({"model": MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read().decode())
    return data.get("embedding", [])

def main():
    log.info(f"Cargando catálogo desde {CATALOG_PATH}")
    with open(CATALOG_PATH, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    log.info(f"Generando embeddings para {len(items)} ítems con {MODEL}...")

    ids = []
    titles = []
    all_embeddings = []

    for i, item in enumerate(items):
        item_id = item.get("id", f"item-{i}")
        ids.append(item_id)
        titles.append(item.get("title", ""))

        # Texto para embedizar: título + descripción + tags
        text_parts = [
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("tags", [])),
        ]
        text = " | ".join(p for p in text_parts if p).strip()
        if not text:
            text = item_id

        all_embeddings.append(_get_embedding(text))

        if (i + 1) % BATCH_SIZE == 0 or i == len(items) - 1:
            log.info(f"  [{i+1}/{len(items)}] embeddings generados")

        if i < len(items) - 1:
            time.sleep(SLEEP_BETWEEN)

    # Guardar
    import numpy as np
    mat = np.array(all_embeddings, dtype=np.float32)
    np.save(str(EMBED_DIR / "embeddings.npy"), mat)

    with open(EMBED_DIR / "embedding_ids.json", "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    with open(EMBED_DIR / "embedding_titles.json", "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False)

    log.info(f"✅ Embeddings guardados: {mat.shape} matriz float32")
    log.info(f"   {len(ids)}  IDs en embedding_ids.json")
    log.info(f"   Archivos en: {EMBED_DIR}")

if __name__ == "__main__":
    main()
