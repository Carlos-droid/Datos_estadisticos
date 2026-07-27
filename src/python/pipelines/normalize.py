#!/usr/bin/env python3
"""Pipeline de normalización — raw/ → processed/ → catálogo unificado.

Lee datos crudos de las 3 fuentes (Funcas, BBVA, INE) y produce:
  processed/catalog.jsonl       → Catálogo unificado (todos los ítems)
  processed/funcas_clean.jsonl  → Documentos Funcas normalizados
  processed/bbva_clean.jsonl    → Publicaciones BBVA normalizadas
  processed/ine_clean.jsonl     → Operaciones INE normalizadas

Formato de salida (catalog.jsonl):
  { id, source, title, date_iso, description, tags, url, type, extra }
"""
import json, os, sys, re
from datetime import datetime, timezone
from pathlib import Path

# Config portable
_this_dir = Path(__file__).resolve().parent  # src/python/pipelines/
_repo_root = _this_dir.parent.parent.parent   # repositorio-okf-economia/
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.python.config import (
    BASE_DIR, FUNCAS_DIR, BBVA_DIR, INE_DIR, source_dirs,
)
from src.python.log_utils import ScrapeLogger

log = ScrapeLogger("normalize", "PIPELINE")

# Directorios de salida
FUNCAS_RAW  = source_dirs(FUNCAS_DIR)["raw"]
BBVA_RAW    = source_dirs(BBVA_DIR)["raw"]
INE_RAW     = source_dirs(INE_DIR)["raw"]

FUNCAS_OKF  = source_dirs(FUNCAS_DIR)["okf"]
BBVA_OKF    = source_dirs(BBVA_DIR)["okf"]
INE_OKF     = source_dirs(INE_DIR)["okf"]

PROC_DIR    = BASE_DIR / "processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. Normalizar Funcas
# ---------------------------------------------------------------------------
def normalize_funcas() -> list[dict]:
    """Lee docs.jsonl + OKF bundles y produce registros normalizados."""
    items = []
    jsonl_path = FUNCAS_RAW / "docs.jsonl"
    if not jsonl_path.exists():
        log.warning("Funcas raw/docs.jsonl no existe", path=str(jsonl_path))
        return items

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            slug = doc.get("id", "")

            # Leer el OKF bundle para obtener título real y descripción
            okf_path = FUNCAS_OKF / "conceptos" / f"{slug}.md"
            title = doc.get("title", "") or slug
            description = ""
            url = doc.get("url", "")
            if okf_path.exists():
                content = okf_path.read_text(encoding="utf-8")
                # Extraer title del YAML frontmatter
                m = re.search(r'^title:\s*"(.+)"$', content, re.MULTILINE)
                if m:
                    title = m.group(1)
                # Extraer description del YAML
                m = re.search(r'^description:\s*"(.+)"$', content, re.MULTILINE)
                if m:
                    description = m.group(1)
                # Extraer URL del body: **URL:** [texto](url)
                m2 = re.search(r'\*\*URL:\*\*\s*\[.+?\]\((.+?)\)', content)
                if m2 and not url:
                    url = m2.group(1)
                # Si no hay descripción, extraer el resumen del body
                if not description:
                    m3 = re.search(r'## Resumen\s*\n+(.*?)(?=\n##|$)', content, re.DOTALL)
                    if m3:
                        description = m3.group(1).strip()[:500]

            # Limpiar fecha
            date_raw = doc.get("date", "") or doc.get("lastmod", "")
            date_iso = _parse_date_iso(date_raw)

            authors_raw = doc.get("author_raw", "")
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()] if authors_raw else []

            items.append({
                "id": f"funcas-{slug}",
                "source": "Funcas",
                "title": title,
                "date_iso": date_iso,
                "description": description,
                "tags": ["economía", "españa", "funcas"],
                "url": url,
                "pdf_url": doc.get("pdf_url", ""),
                "authors": authors,
                "date_raw": date_raw,
                "type": "working_paper",
                "normalized_at": _now_iso(),
            })

    log.info(f"Funcas: {len(items)} documentos normalizados")
    return items


# ---------------------------------------------------------------------------
# 2. Normalizar BBVA
# ---------------------------------------------------------------------------
def normalize_bbva() -> list[dict]:
    """Lee docs.jsonl + OKF bundles BBVA."""
    items = []
    jsonl_path = BBVA_RAW / "docs.jsonl"
    if not jsonl_path.exists():
        log.warning("BBVA raw/docs.jsonl no existe", path=str(jsonl_path))
        return items

    # IDs de páginas de sistema (no publicaciones reales)
    SYSTEM_PAGES = {
        "centro-de-preferencia-de-la-privacidad",
        "lista-de-cookies",
        "configuraci-n-de-cookies",
        "publicaciones-m-s-recientes",
        "publicaciones-m-s-recientes-de-espa-a",
        "publicaciones-m-s-recientes-sobre-big-da",
    }

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            slug = doc.get("id", "")

            # Saltar páginas de sistema (no son publicaciones reales)
            if slug in SYSTEM_PAGES:
                continue

            # Leer OKF bundle para título real + URL
            okf_path = BBVA_OKF / "conceptos" / f"{slug}.md"
            title = doc.get("title", "") or slug
            description = ""
            url = doc.get("url", "")
            if okf_path.exists():
                content = okf_path.read_text(encoding="utf-8")
                m = re.search(r'^title:\s*"(.+)"$', content, re.MULTILINE)
                if m:
                    title = m.group(1)
                m = re.search(r'^description:\s*"(.+)"$', content, re.MULTILINE)
                if m:
                    description = m.group(1)
                # Extraer URL del YAML frontmatter
                m4 = re.search(r'^url:\s*"(.+)"$', content, re.MULTILINE)
                if m4 and m4.group(1) and not url:
                    url = m4.group(1)

            # Generar URL desde slug si no se encontró
            if not url:
                url = f"https://www.bbvaresearch.com/publicaciones/{slug}/"

            date_raw = doc.get("date_raw", "")
            date_iso = _parse_date_iso(date_raw)
            geography = ""
            if "espana" in slug.lower() or "españa" in slug.lower():
                geography = "España"
            elif "global" in slug.lower():
                geography = "Global"

            items.append({
                "id": f"bbva-{slug}",
                "source": "BBVA Research",
                "title": title,
                "date_iso": date_iso,
                "description": description,
                "tags": ["economía", geography] if geography else ["economía"],
                "url": url,
                "geography": geography,
                "technique": doc.get("technique", ""),
                "date_raw": date_raw,
                "type": "report",
                "normalized_at": _now_iso(),
            })

    log.info(f"BBVA: {len(items)} publicaciones normalizadas")
    return items


# ---------------------------------------------------------------------------
# 3. Normalizar INE
# ---------------------------------------------------------------------------
def normalize_ine() -> list[dict]:
    """Lee operaciones.jsonl + tablas y produce registros normalizados."""
    items = []
    ops_path = INE_RAW / "operaciones.jsonl"
    if not ops_path.exists():
        log.warning("INE raw/operaciones.jsonl no existe", path=str(ops_path))
        return items

    # Leer catálogo maestro INE
    index_path = INE_OKF / "index.md"
    index_content = ""
    if index_path.exists():
        index_content = index_path.read_text(encoding="utf-8")

    # Extraer pares código → nombre desde index.md
    op_map = {}
    for m in re.finditer(
        r'\|\s*\*\*(\w+)\*\*\s*\|\s*([^|]+?)\s*\|', index_content
    ):
        op_map[m.group(1)] = m.group(2).strip()

    with open(ops_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            op = json.loads(line)
            code = op.get("Codigo", "")
            name = op.get("Nombre", "")
            op_id = op.get("Id", "")

            # Buscar tablas asociadas
            tables_path = INE_RAW / f"tables_op{op_id}.jsonl"
            table_count = 0
            if tables_path.exists():
                with open(tables_path, encoding="utf-8") as tf:
                    table_count = sum(1 for _ in tf if _.strip())

            # Descripción desde el catálogo o la propia operación
            description = op_map.get(code, name)

            # URL desde el OKF bundle
            url = ""
            okf_path = INE_OKF / "conceptos" / f"{code.lower()}.md"
            if okf_path.exists():
                okf_content = okf_path.read_text(encoding="utf-8")
                m4 = re.search(r'^url:\s*"(.+)"$', okf_content, re.MULTILINE)
                if m4:
                    url = m4.group(1)

            # Fecha: última modificación desde tablas
            date_iso = ""
            if tables_path.exists():
                with open(tables_path, encoding="utf-8") as tf:
                    for tl in tf:
                        tl = tl.strip()
                        if not tl:
                            continue
                        tbl = json.loads(tl)
                        mod = tbl.get("Ultima_Modificacion", "")
                        if mod:
                            date_iso = _parse_ine_date(mod)
                            break

            items.append({
                "id": f"ine-{code.lower()}" if code else f"ine-op{op_id}",
                "source": "INE",
                "title": name,
                "date_iso": date_iso,
                "description": description,
                "tags": ["INE", "economía española", code.lower()] if code else ["INE"],
                "url": url,
                "operation_id": op_id,
                "operation_code": code,
                "tables_count": table_count,
                "type": "dataset",
                "normalized_at": _now_iso(),
            })

    log.info(f"INE: {len(items)} operaciones normalizadas")
    return items


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _parse_date_iso(raw: str) -> str:
    """Intenta parsear una fecha a ISO 8601 (YYYY-MM-DD)."""
    if not raw:
        return ""
    # Intentar formatos comunes
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d de %B de %Y",
        "%B %Y",
        "%Y",
    ]:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Si tiene año suelto
    m = re.search(r"(\d{4})", raw)
    if m:
        return m.group(1)
    return raw[:10] if raw else ""


def _parse_ine_date(mod: str) -> str:
    """Convierte timestamp INE (Unix ms) a ISO."""
    try:
        ms = int(mod)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return str(mod)[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 4. Catálogo unificado
# ---------------------------------------------------------------------------
def build_catalog(all_items: list[dict]):
    """Escribe catalog.jsonl con todos los ítems normalizados."""
    cat_path = PROC_DIR / "catalog.jsonl"
    with open(cat_path, "w", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Estadísticas
    from collections import Counter
    sources = Counter(item["source"] for item in all_items)
    types = Counter(item["type"] for item in all_items)
    log.info(f"Catálogo: {len(all_items)} ítems")
    for src, count in sources.most_common():
        log.info(f"  {src}: {count}")
    log.info(f"  Tipos: {dict(types)}")
    log.info(f"  Archivo: {cat_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=== Normalización raw/ → processed/ ===")

    funcas_items = normalize_funcas()
    bbva_items   = normalize_bbva()
    ine_items    = normalize_ine()

    # Guardar por fuente
    _save_jsonl(PROC_DIR / "funcas_clean.jsonl", funcas_items)
    _save_jsonl(PROC_DIR / "bbva_clean.jsonl",   bbva_items)
    _save_jsonl(PROC_DIR / "ine_clean.jsonl",    ine_items)

    # Catálogo unificado
    all_items = sorted(
        funcas_items + bbva_items + ine_items,
        key=lambda x: x.get("date_iso", ""),
        reverse=True,
    )
    build_catalog(all_items)

    # Resumen
    log.info(f"✅ Normalización completa")
    log.info(f"   Funcas:  {len(funcas_items)} docs")
    log.info(f"   BBVA:    {len(bbva_items)} pubs")
    log.info(f"   INE:     {len(ine_items)} ops")
    log.info(f"   Total:   {len(all_items)} registros en catalog.jsonl")
    log.info(f"   Destino: {PROC_DIR}")


def _save_jsonl(path: Path, items: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
