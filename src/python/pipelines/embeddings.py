#!/usr/bin/env python3
"""Genera embeddings semánticos para catalog.jsonl usando Ollama (batch).

Usa /api/embed con lotes de 50 items para eficiencia.
Modelo: nomic-embed-text (262MB, 768d) más estable que v2-moe.

Salida:
  processed/embeddings.npy      → Matriz numpy (N x 768)
  processed/embedding_ids.json  → Lista de IDs en el mismo orden
  processed/embedding_titles.json → Títulos para mostrar resultados
"""
import json, sys, time
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_repo_root = _this_dir.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.python.config import BASE_DIR
from src.python.log_utils import ScrapeLogger

log = ScrapeLogger("embeddings", "EMBED")

CATALOG_PATH = BASE_DIR / "processed" / "catalog.jsonl"
EMBED_DIR = BASE_DIR / "processed"
MODEL = "nomic-embed-text"  # 262MB, más estable que v2-moe
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 1.0  # 1s entre lotes
MAX_RETRIES = 3


def _batch_embed(texts: list[str]) -> list[list[float]]:
    """Llama a Ollama /api/embed con un lote de textos."""
    import urllib.request
    payload = json.dumps({"model": MODEL, "input": texts}).encode()
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read().decode())
            result = data.get("embeddings", [])
            if not result:
                raise ValueError("Respuesta vacía")
            return result
        except (urllib.error.HTTPError, urllib.error.URLError,
                json.JSONDecodeError, OSError, ValueError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = 2 ** attempt * 2  # 2s, 4s, 8s
                log.warning(f"Reintento {attempt+1}/{MAX_RETRIES} en {delay}s: {e}")
                time.sleep(delay)
            else:
                raise


def main():
    log.info(f"Cargando catálogo desde {CATALOG_PATH}")
    with open(CATALOG_PATH, encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]

    log.info(f"Generando embeddings para {len(items)} ítems con {MODEL} "
             f"(batch={BATCH_SIZE})...")

    ids = []
    titles = []
    all_embeddings = []
    n_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(n_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(items))
        batch = items[start:end]

        # Preparar textos para embedizar
        batch_texts = []
        for item in batch:
            text_parts = [
                item.get("title", ""),
                item.get("description", ""),
                " ".join(item.get("tags", [])),
            ]
            text = " | ".join(p for p in text_parts if p).strip()
            if not text:
                text = item.get("id", f"item-{start}")
            batch_texts.append(text)

        try:
            embs = _batch_embed(batch_texts)
        except Exception as e:
            log.error(f"Error en lote {batch_idx+1}/{n_batches}: {e}")
            # Si falla, intentar de uno en uno como fallback
            embs = []
            for j, t in enumerate(batch_texts):
                try:
                    result = _batch_embed([t])
                    embs.append(result[0])
                except Exception as e2:
                    log.error(f"  Item {start+j+1}: error irrecuperable: {e2}")
                    embs.append([0.0] * 768)  # zero vector como placeholder

        for j, item in enumerate(batch):
            ids.append(item.get("id", f"item-{start+j}"))
            titles.append(item.get("title", ""))
            if j < len(embs):
                all_embeddings.append(embs[j])
            else:
                all_embeddings.append([0.0] * 768)

        if (batch_idx + 1) % 5 == 0 or batch_idx == n_batches - 1 or batch_idx == 0:
            log.info(f"  [{end}/{len(items)}] lote {batch_idx+1}/{n_batches}")

        if batch_idx < n_batches - 1:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    # Guardar
    import numpy as np
    mat = np.array(all_embeddings, dtype=np.float32)
    np.save(str(EMBED_DIR / "embeddings.npy"), mat)

    with open(EMBED_DIR / "embedding_ids.json", "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    with open(EMBED_DIR / "embedding_titles.json", "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False)

    log.info(f"✅ Embeddings guardados: {mat.shape} matriz float32")
    log.info(f"   {len(ids)} IDs en embedding_ids.json")
    log.info(f"   Archivos en: {EMBED_DIR}")


if __name__ == "__main__":
    main()
