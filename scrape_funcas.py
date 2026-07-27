#!/usr/bin/env python3
"""Funcas scraper: extract all working documents & technical notes via sitemap + crawl4ai"""

import json, os, sys, time, re, subprocess, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path("/mnt/hdd/repositorio-okf-economia/funcas")
RAW_DIR = BASE_DIR / "raw"
PDF_DIR = RAW_DIR / "pdfs"
PROC_DIR = BASE_DIR / "processed"
OKF_DIR = BASE_DIR / "okf"
CONCEPTOS_DIR = OKF_DIR / "conceptos"

for d in [RAW_DIR, PDF_DIR, PROC_DIR, OKF_DIR, CONCEPTOS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CRWL = "crwl crawl"
CRWL_ENV = os.environ.copy()
CRWL_ENV["PATH"] = f"/home/ia/.hermes/profiles/blogs/home/.local/bin:{os.environ.get('PATH', '')}"

def run_crwl(url, timeout=60):
    """Run crawl4ai CLI and return markdown output"""
    cmd = f"{CRWL} {url} -o md"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=CRWL_ENV)
        return r.stdout
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {url}")
        return ""
    except Exception as e:
        print(f"  ERROR: {e}")
        return ""

def fetch_sitemap():
    """Get all document URLs from the WordPress sitemap"""
    sitemap_url = "https://www.funcas.es/wp-sitemap-posts-documentos_trabajo-1.xml"
    print(f"📡 Fetching sitemap: {sitemap_url}")
    try:
        req = urllib.request.Request(sitemap_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        xml_data = resp.read()
        root = ET.fromstring(xml_data)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        docs = []
        for url_elem in root.findall("sm:url", ns):
            loc = url_elem.find("sm:loc", ns)
            lastmod = url_elem.find("sm:lastmod", ns)
            if loc is not None:
                docs.append({
                    "url": loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod is not None else ""
                })
        print(f"  → {len(docs)} documents found in sitemap")
        return docs
    except Exception as e:
        print(f"  ERROR fetching sitemap: {e}")
        return []

def extract_metadata_from_listing():
    """Extract document metadata from the listing page (faster than individual pages)"""
    listing_url = "https://www.funcas.es/publicaciones/documentos-de-trabajo-y-notas-tecnicas/listado-de-documentos-de-trabajo-y-notas-tecnicas/"
    print(f"📡 Fetching listing page...")
    md = run_crwl(listing_url, timeout=90)
    
    docs = []
    # Parse the markdown output to find document entries
    # Pattern: ## [Title](url) followed by Fecha: month/year and Author
    lines = md.split('\n')
    current = None
    
    for i, line in enumerate(lines):
        # Heading with link = document title
        if line.startswith('## [') and line.strip().endswith(']'):
            # Extract title and URL
            m = re.match(r'## \[(.+?)\]\((.+?)\)', line)
            if m:
                if current and current.get('title'):
                    docs.append(current)
                current = {
                    'title': m.group(1).strip(),
                    'url': m.group(2).strip(),
                    'source': 'Funcas',
                    'scraped_at': datetime.now(timezone.utc).isoformat()
                }
        elif current and 'Fecha:' in line:
            m = re.search(r'([a-z]+ \d{4})', line.lower())
            if m:
                current['date'] = m.group(1).capitalize()
        elif current and current.get('title') and line.strip() and not line.startswith('#') and not line.startswith('[') and not line.startswith('!') and not line.startswith('*'):
            # Could be author or abstract
            if 'autores' not in current and len(line.strip()) < 100 and not line.startswith('http'):
                # Check if it looks like a name (not too long, no bullets)
                if not any(kw in line.lower() for kw in ['fecha', 'versión', 'download', 'pdf', 'política', 'funcas', 'publicaciones']):
                    current['author_raw'] = line.strip()
    
    if current and current.get('title'):
        docs.append(current)
    
    return docs

def extract_single_doc(url):
    """Extract detailed metadata from a single document page"""
    md = run_crwl(url, timeout=45)
    if not md:
        return {}
    
    result = {'url': url}
    
    # Title from the page H1
    m = re.search(r'# (.+)', md)
    if m:
        result['title'] = m.group(1).strip()
    
    # Find PDF links
    pdfs = re.findall(r'https://www\.funcas\.es/wp-content/uploads/[^"\')\s]+\.pdf', md)
    if pdfs:
        result['pdf_url'] = pdfs[0]
    if len(pdfs) > 1:
        result['pdf_url_en'] = pdfs[1] if 'english' in md.lower() or 'inglés' in md.lower() else None
    
    # Extract abstract - text after title/description
    abstract_match = re.search(r'Resumen:(.+?)(?:##|$)', md, re.DOTALL)
    if abstract_match:
        result['abstract'] = abstract_match.group(1).strip()
    
    # Try to find author and date patterns
    lines = md.split('\n')
    for i, line in enumerate(lines):
        if 'Fecha:' in line:
            m2 = re.search(r'\*\*(.+?)\*\*', line)
            if m2:
                result['date'] = m2.group(1).strip()
    
    return result

def download_pdf(pdf_url, doc_id):
    """Download a PDF file"""
    if not pdf_url:
        return None
    filename = f"{doc_id}.pdf"
    filepath = PDF_DIR / filename
    if filepath.exists():
        return filepath
    
    try:
        req = urllib.request.Request(pdf_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.funcas.es/"
        })
        resp = urllib.request.urlopen(req, timeout=60)
        data = resp.read()
        filepath.write_bytes(data)
        return filepath
    except Exception as e:
        print(f"  ⚠ PDF download failed: {e}")
        return None

def create_okf_bundle(doc, doc_id):
    """Create an OKF markdown file for a document"""
    title = doc.get('title', 'Sin título').replace('"', "'")
    desc = doc.get('abstract', doc.get('description', '')).replace('"', "'")
    authors = doc.get('authors', [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(';')]
    
    date_raw = doc.get('date', doc.get('scraped_at', '')[:7])
    date_iso = date_raw[:7] if date_raw else ''
    
    pdf_url = doc.get('pdf_url', '')
    pdf_local = doc.get('pdf_local', '')
    
    tags = ['economía', 'españa', 'funcas']
    if 'técnica' in title.lower() or 'técnica' in desc.lower() or 'nota técnica' in title.lower():
        doc_type = 'nota_tecnica'
        tags.append('nota técnica')
    else:
        doc_type = 'documento_trabajo'
        tags.append('documento de trabajo')
    
    okf_content = f"""---
okf_version: "1.0.0"
title: "{title}"
description: "{desc[:500]}"
source: "Funcas"
type: "{doc_type}"
authors: {json.dumps(authors)}
date: "{date_iso}"
published: "{doc.get('lastmod', doc.get('scraped_at', ''))}"
lang: "es"
url: "{doc.get('url', '')}"
pdf_url: "{pdf_url}"
pdf_path: "{pdf_local}"
tags: {json.dumps(tags)}
scraped_at: "{doc.get('scraped_at', datetime.now(timezone.utc).isoformat())}"
okf_concept: "funcas/documents/{doc_id}"
---

# {title}

## Resumen

{desc[:2000]}

## Metadatos

- **Fuente:** {doc.get('source', 'Funcas')}
- **Tipo:** {doc_type}
- **Fecha:** {date_iso}
- **Autores:** {', '.join(authors) if authors else 'No especificado'}
- **URL:** [{doc.get('url', '')}]({doc.get('url', '')})
- **PDF:** [{pdf_url}]({pdf_url})

## Contenido

Documento de investigación económica publicado por Funcas.
"""
    
    okf_path = CONCEPTOS_DIR / f"{doc_id}.md"
    okf_path.write_text(okf_content)
    return okf_path

def build_index(docs):
    """Build the OKF index.md"""
    lines = [
        "---",
        'okf_version: "1.0.0"',
        'title: "Funcas - Documentos de Trabajo y Notas Técnicas"',
        'description: "Repositorio OKF de publicaciones económicas de Funcas (932+ documentos, 2007-2026)"',
        'source: "Funcas"',
        'type: "collection"',
        f'total_documents: {len(docs)}',
        f'scraped_at: "{datetime.now(timezone.utc).isoformat()}"',
        'tags: ["funcas", "economía española", "documentos de trabajo", "notas técnicas"]',
        "---",
        "",
        "# Funcas - Catálogo de Documentos",
        "",
        f"Total: **{len(docs)} documentos** | Rango: 2007–2026 | Fuente: [Funcas](https://www.funcas.es)",
        "",
        "## Por año",
    ]
    
    # Group by year
    by_year = {}
    for d in docs:
        yr = d.get('date', '')[:4] if d.get('date') else 'sin_fecha'
        by_year.setdefault(yr, []).append(d)
    
    for yr in sorted(by_year.keys(), reverse=True):
        items = by_year[yr]
        lines.append(f"\n### {yr} ({len(items)} documentos)\n")
        for d in items:
            title = d.get('title', 'Sin título')
            doc_id = d.get('id', '')
            authors = d.get('authors', d.get('author_raw', ''))
            if isinstance(authors, list):
                authors = ', '.join(authors[:2]) + (' et al.' if len(authors) > 2 else '')
            lines.append(f'- [{title}](conceptos/{doc_id}.md) — {authors}')
    
    index_path = OKF_DIR / "index.md"
    index_path.write_text('\n'.join(lines))
    return index_path

def build_log():
    """Build the OKF log.md"""
    log = f"""---
okf_version: "1.0.0"
title: "Funcas - Registro de cambios"
---

# Registro de cambios

| Fecha | Acción | Detalle |
|---|---|---|
| {datetime.now().strftime('%Y-%m-%d %H:%M')} | Scraping inicial | Extracción masiva de documentos vía sitemap + crawl4ai |
"""
    log_path = OKF_DIR / "log.md"
    log_path.write_text(log)
    return log_path

def main():
    print("=" * 60)
    print("FUNCAS SCRAPER — Documentos de Trabajo y Notas Técnicas")
    print("=" * 60)
    
    # Phase 1: Get sitemap URLs
    sitemap_docs = fetch_sitemap()
    if not sitemap_docs:
        print("⚠ Sitemap empty, falling back to listing page")
        # Fall back to listing page extraction
    
    # Phase 2: Get metadata from listing page (faster)
    print("\n📋 Extracting metadata from listing page...")
    listing_docs = extract_metadata_from_listing()
    print(f"  → {len(listing_docs)} documents found in listing")
    
    # Merge: use sitemap URLs + listing metadata
    all_docs = []
    seen_urls = set()
    
    for sd in sitemap_docs:
        url = sd['url']
        # Extract slug for ID
        slug = url.rstrip('/').split('/')[-1]
        doc_id = slug[:50]
        
        # Find matching listing doc
        listing_match = None
        for ld in listing_docs:
            if ld.get('url') == url or ld.get('url', '').rstrip('/').split('/')[-1] == slug:
                listing_match = ld
                break
        
        doc = {
            'id': doc_id,
            'url': url,
            'lastmod': sd['lastmod'],
            'title': listing_match.get('title', '') if listing_match else '',
            'author_raw': listing_match.get('author_raw', '') if listing_match else '',
            'date': listing_match.get('date', '') if listing_match else '',
            'source': 'Funcas',
            'scraped_at': datetime.now(timezone.utc).isoformat()
        }
        all_docs.append(doc)
        seen_urls.add(url)
    
    print(f"\n📊 Total documents to process: {len(all_docs)}")
    
    # Phase 3: For recent documents, fetch individual pages for PDF and full metadata
    # Focus on 2024-2026 first (most relevant)
    print("\n🔍 Fetching individual details for recent documents (2024-2026)...")
    for i, doc in enumerate(all_docs):
        year = doc.get('lastmod', '')[:4] if doc.get('lastmod') else doc.get('date', '')[:4]
        if year in ('2024', '2025', '2026'):
            print(f"  [{i+1}/{len(all_docs)}] {doc.get('title', 'No title')[:60]}...")
            details = extract_single_doc(doc['url'])
            if details.get('pdf_url'):
                doc['pdf_url'] = details['pdf_url']
                if details.get('pdf_url_en'):
                    doc['pdf_url_en'] = details['pdf_url_en']
            if details.get('abstract'):
                doc['abstract'] = details.get('abstract', '')
            
            # Download PDF
            if doc.get('pdf_url'):
                pdf_path = download_pdf(doc['pdf_url'], doc['id'])
                if pdf_path:
                    doc['pdf_local'] = str(pdf_path)
                    doc['pdf_size'] = pdf_path.stat().st_size
            
            time.sleep(1.5)  # Rate limiting
    
    # Phase 4: Save raw JSONL
    jsonl_path = RAW_DIR / "docs.jsonl"
    with open(jsonl_path, 'w') as f:
        for doc in all_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
    print(f"\n💾 Saved raw metadata: {jsonl_path}")
    
    # Phase 5: Create OKF bundles
    print("\n📝 Creating OKF bundles...")
    okf_count = 0
    for doc in all_docs:
        try:
            create_okf_bundle(doc, doc['id'])
            okf_count += 1
        except Exception as e:
            print(f"  ⚠ Error creating OKF for {doc.get('id', '?')}: {e}")
    
    build_index(all_docs)
    build_log()
    
    print(f"\n✅ COMPLETE!")
    print(f"   Documents: {len(all_docs)}")
    print(f"   OKF bundles: {okf_count}")
    print(f"   PDFs downloaded: {len(list(PDF_DIR.glob('*.pdf')))}")
    print(f"   Location: {BASE_DIR}")

if __name__ == "__main__":
    main()
