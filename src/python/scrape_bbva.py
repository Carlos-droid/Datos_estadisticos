#!/usr/bin/env python3
"""BBVA Research scraper — publicaciones, Big Data, España."""

import json, os, sys, time, re, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Config portable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.python.config import BASE_DIR as REPO_DIR, BBVA_DIR, source_dirs
from src.python.log_utils import ScrapeLogger

log = ScrapeLogger("scrape_bbva", "BBVA")

BASE_DIR = BBVA_DIR
RAW_DIR  = source_dirs(BBVA_DIR)["raw"]
PROC_DIR = source_dirs(BBVA_DIR)["processed"]
OKF_DIR  = source_dirs(BBVA_DIR)["okf"]
CONCEPTOS_DIR = source_dirs(BBVA_DIR)["conceptos"]

for d in [RAW_DIR, PDF_DIR := source_dirs(BBVA_DIR)["raw_pdfs"], PROC_DIR, OKF_DIR, CONCEPTOS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CRWL_ENV = os.environ.copy()
crwl_path = os.environ.get("CRWL_PATH", "")
if crwl_path:
    CRWL_ENV["PATH"] = f"{crwl_path}:{os.environ.get('PATH', '')}"

def crwl(url, timeout=60):
    cmd = f"crwl crawl {url} -o md"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=CRWL_ENV)
        return r.stdout
    except:
        return ""

def fetch_bbva_publications(base_url, label=""):
    """Fetch BBVA publications from a listing page"""
    print(f"\n📋 Fetching {label}...")
    md = crwl(base_url, timeout=60)
    if not md:
        return []
    
    docs = []
    # BBVA articles pattern: article blocks with headings and descriptions
    # Pattern: heading "España | Title" or "Global | Title"
    lines = md.split('\n')
    current = None
    
    for line in lines:
        # Heading level 3 = article title
        if line.startswith('### ') or line.startswith('## '):
            title_text = line.lstrip('# ')
            if current and current.get('title'):
                docs.append(current)
            current = {'title': title_text.strip(), 'source': 'BBVA Research'}
        elif current and current.get('title'):
            # Look for date pattern (dd month yyyy or dd/mm/yyyy)
            date_m = re.search(r'(\d{1,2}\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})', line.lower())
            if date_m:
                current['date_raw'] = date_m.group(1)
            
            # Look for links to articles  
            link_m = re.findall(r'(?:href=")?(https?://www\.bbvaresearch\.com/[^"\s)]+)', line)
            if link_m:
                current['url'] = link_m[0]
            
            # Detect geography in title
            geo_m = re.match(r'(España|Global|México|Turquía|Colombia|Argentina|Perú|EEUU|Europa|China)\s*[|]', current['title'])
            if geo_m:
                current['geography'] = geo_m.group(1)
            
            # Detect technique
            if 'Con técnicas Big Data' in line or 'Con técnicas Big Data' in current.get('title', ''):
                current['technique'] = 'big-data'
    
    if current and current.get('title'):
        docs.append(current)
    
    return docs

def download_pdf(url, doc_id):
    """Try to download a PDF"""
    if not url or not url.endswith('.pdf'):
        return None
    filepath = PDF_DIR / f"{doc_id}.pdf"
    if filepath.exists():
        return filepath
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read()
        filepath.write_bytes(data)
        return filepath
    except:
        return None

def create_okf(doc, doc_id):
    """Create OKF markdown bundle"""
    title = doc.get('title', 'Sin título').replace('"', "'")
    desc = doc.get('description', doc.get('abstract', '')).replace('"', "'")
    
    tags = ['BBVA Research', 'economía', doc.get('geography', '').lower() or 'españa']
    if doc.get('technique') == 'big-data':
        tags.append('big data')
        tags.append('IA')
    
    doc_type = doc.get('type', 'informe')
    geo = doc.get('geography', '')
    
    okf_content = f"""---
okf_version: "1.0.0"
title: "{title}"
description: "{desc[:500]}"
source: "BBVA Research"
type: "{doc_type}"
geography: "{geo}"
technique: "{doc.get('technique', '')}"
date: "{doc.get('date_raw', '')}"
url: "{doc.get('url', '')}"
pdf_url: "{doc.get('pdf_url', '')}"
tags: {json.dumps(tags)}
scraped_at: "{datetime.now(timezone.utc).isoformat()}"
okf_concept: "bbva/documents/{doc_id}"
---

# {title}

## Metadatos

- **Fuente:** BBVA Research
- **Geografía:** {geo or 'No especificada'}
- **Técnica:** {doc.get('technique', 'Convencional')}
- **Fecha:** {doc.get('date_raw', '')}
- **URL:** [{doc.get('url', '')}]({doc.get('url', '')})
"""
    
    okf_path = CONCEPTOS_DIR / f"{doc_id}.md"
    okf_path.write_text(okf_content)
    return okf_path

def search_working_papers():
    """Search for BBVA working papers via known patterns"""
    print("\n🔍 Searching for working papers...")
    # Try the filter URL
    md = crwl("https://www.bbvaresearch.com/publicaciones/?_tipo_publicacion=documento-de-trabajo", timeout=45)
    # Extract potential WP titles
    wps = []
    if md:
        for line in md.split('\n'):
            if 'Working Paper' in line or 'Documento de Trabajo' in line or 'WP_' in line:
                wps.append(line.strip()[:120])
    return wps

def main():
    print("=" * 60)
    print("BBVA RESEARCH SCRAPER")
    print("=" * 60)
    
    all_docs = []
    
    # 1. Big Data Publications (4 pages)
    sources = [
        ("https://www.bbvaresearch.com/big-data/publicaciones/", "Big Data Publications"),
        ("https://www.bbvaresearch.com/geography/espana/", "Spain Publications"),
        ("https://www.bbvaresearch.com/tag/big-data/", "Big Data Tag"),
    ]
    
    for url, label in sources:
        docs = fetch_bbva_publications(url, label)
        for d in docs:
            d['source_url'] = url
            d['scraped_at'] = datetime.now(timezone.utc).isoformat()
        all_docs.extend(docs)
        print(f"  → {len(docs)} from {label}")
        time.sleep(2)
    
    # Deduplicate by title
    seen = set()
    unique_docs = []
    for d in all_docs:
        key = d.get('title', '').strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique_docs.append(d)
    
    print(f"\n📊 Total unique documents: {len(unique_docs)}")
    
    # Save raw JSONL
    jsonl_path = RAW_DIR / "docs.jsonl"
    with open(jsonl_path, 'w') as f:
        for doc in unique_docs:
            doc['id'] = re.sub(r'[^a-z0-9]+', '-', doc.get('title', 'doc')[:40].lower()).strip('-')
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    
    # Create OKF bundles
    for doc in unique_docs:
        create_okf(doc, doc['id'])
    
    # Build index
    index_lines = [
        "---",
        'okf_version: "1.0.0"',
        'title: "BBVA Research - Publicaciones"',
        f'description: "Repositorio OKF de publicaciones económicas de BBVA Research ({len(unique_docs)} documentos)"',
        'source: "BBVA Research"',
        'type: "collection"',
        f'total_documents: {len(unique_docs)}',
        f'scraped_at: "{datetime.now(timezone.utc).isoformat()}"',
        'tags: ["BBVA Research", "economía", "big data", "españa"]',
        "---",
        "",
        "# BBVA Research - Catálogo de Publicaciones",
        "",
        f"Total: **{len(unique_docs)} publicaciones** | Fuente: [BBVA Research](https://www.bbvaresearch.com)",
        "",
        "## Publicaciones",
    ]
    for d in unique_docs:
        index_lines.append(f'- [{d.get("title", "?")}](conceptos/{d.get("id", "?")}.md) — {d.get("date_raw", "")} {d.get("geography", "")}')
    
    (OKF_DIR / "index.md").write_text('\n'.join(index_lines))
    
    # Log
    log = f"""---
okf_version: "1.0.0"
title: "BBVA Research - Registro de cambios"
---
# Registro
| Fecha | Acción | Detalle |
|---|---|---|
| {datetime.now().strftime('%Y-%m-%d %H:%M')} | Scraping inicial | {len(unique_docs)} documentos extraídos |
"""
    (OKF_DIR / "log.md").write_text(log)
    
    print(f"\n✅ BBVA Complete!")
    print(f"   Documents: {len(unique_docs)}")
    print(f"   Location: {BASE_DIR}")

if __name__ == "__main__":
    main()
