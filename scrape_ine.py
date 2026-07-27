#!/usr/bin/env python3
"""INE Data Agent: extract all statistical operations, tables, and data via JSON API"""

import json, os, sys, time, re, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path("/mnt/hdd/repositorio-okf-economia/ine")
RAW_DIR = BASE_DIR / "raw"
PROC_DIR = BASE_DIR / "processed"
OKF_DIR = BASE_DIR / "okf"
CONCEPTOS_DIR = OKF_DIR / "conceptos"

for d in [RAW_DIR, PROC_DIR, OKF_DIR, CONCEPTOS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

API_BASE = "https://servicios.ine.es/wstempus/js/ES"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}

def api_get(path):
    """Fetch INE API endpoint"""
    url = f"{API_BASE}/{path}" if not path.startswith("http") else path
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"  ⚠ API error [{path}]: {e}")
        return None

def save_jsonl(path, data_list):
    """Save list of dicts as JSONL"""
    with open(path, 'w') as f:
        for item in data_list:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')
    print(f"  💾 Saved: {path}")

# ---------------------------------------------------------------
# Economics-relevant operations
# ---------------------------------------------------------------
ECON_KEY_OPS = [
    25,   # IPC
    18,   # IPCA
    293,  # EPA
    237,  # CNTR (Contabilidad Nacional Trimestral)
    247,  # CNE (Contabilidad Nacional Anual)
    26,   # IPI (Producción Industrial)
    32,   # ICM (Comercio Minorista)
    15,   # IPV (Vivienda)
    432,  # IPVA (Vivienda Alquiler)
    27,   # IPRI (Precios Industriales)
    132,  # IPH (Hoteles)
    48,   # IPRX-M (Exportación/Importación)
    14,   # IPS (Servicios)
    42,   # ICN (Cifras Negocios)
    4,    # EI (Efectos Comercio)
    44,   # ICES (Comercio Internacional Servicios)
    334,  # ETR (Turismo Residentes)
    410,  # VTE (Viviendas Turísticas)
    436,  # TMOV (Turismo móviles)
    61,   # IPAP (Apartamentos Turísticos)
    62,   # IPAC (Camping)
    63,   # IPTR (Turismo Rural)
    137,  # IPT (Precios Trabajo)
    464,  # MOS (Comercio Servicios)
    465,  # STEC (Comercio Servicios Empresas)
]

def fetch_all_operations():
    """Fetch all available operations"""
    print("\n📡 Fetching all operations...")
    data = api_get("OPERACIONES_DISPONIBLES")
    if data:
        save_jsonl(RAW_DIR / "operaciones.jsonl", data)
        print(f"  → {len(data)} operations")
    return data or []

def fetch_tables_for_operation(op_id, op_name):
    """Fetch tables for an operation"""
    print(f"  📊 Tables for {op_name} (id={op_id})...")
    data = api_get(f"TABLAS_OPERACION/{op_id}")
    if data:
        save_jsonl(RAW_DIR / f"tables_op{op_id}.jsonl", data)
    return data or []

def fetch_table_data(table_id, table_name, op_id):
    """Fetch data for a specific table - resumable (skips if already downloaded)"""
    path = RAW_DIR / f"data_op{op_id}_t{table_id}.jsonl"
    if path.exists() and path.stat().st_size > 100:
        # Already downloaded, count existing data
        with open(path) as f:
            count = sum(1 for _ in f)
        print(f"    📈 Data for table {table_id}... (already exists: {count} series)")
        return [], 0  # Skip re-download
    
    print(f"    📈 Data for table {table_id}...")
    data = api_get(f"DATOS_TABLA/{table_id}")
    if data and isinstance(data, list):
        # Save as JSONL
        path = RAW_DIR / f"data_op{op_id}_t{table_id}.jsonl"
        with open(path, 'w') as f:
            for serie in data:
                if isinstance(serie, dict):
                    f.write(json.dumps(serie, ensure_ascii=False, default=str) + '\n')
        # Count total data points
        total_vals = sum(len(s.get('Data', [])) for s in data if isinstance(s, dict))
        print(f"      → {len(data)} series, {total_vals} values")
        return data, total_vals
    elif data:
        print(f"      ⚠ Non-list response (type={type(data).__name__}), skipping")
    return [], 0

def fetch_publications():
    """Fetch all INE publications"""
    print("\n📡 Fetching publications...")
    data = api_get("PUBLICACIONES")
    if data:
        save_jsonl(RAW_DIR / "publicaciones.jsonl", data)
        print(f"  → {len(data)} publications")
    return data or []

# HVD (High Value Datasets) - Direct bulk download
HVD_DATASETS = [
    (11078, "Producción industrial", "IPI"),
    (11079, "IPRI desgloses por actividad", "IPRI"),
    (11080, "Volumen de ventas por actividad", "ICN"),
    (11081, "Flujos turísticos en Europa", "Turismo"),
    (11082, "IPCA", "IPCA"),
    (11083, "PIB principales agregados", "CNTR"),
    (11084, "Indicadores sobre empresas", "CNE"),
    (11085, "Indicadores sobre hogares", "CNE"),
    (11086, "Gastos e ingresos públicos", "Gastos"),
    (11092, "Estadísticas medioambientales", "Medioambiente"),
    (11093, "Población", "Población"),
    (11094, "Fecundidad", "Fecundidad"),
    (11095, "Mortalidad", "Mortalidad"),
    (11096, "Pobreza", "Pobreza"),
    (11097, "Desigualdad", "Desigualdad"),
    (11098, "Dataset HVD 16", "HVD16"),
    (11099, "Dataset HVD 17", "HVD17"),
]

def download_hvd():
    """Download all High Value Datasets in CSV format"""
    HVD_DIR = RAW_DIR / "hvd"
    HVD_DIR.mkdir(exist_ok=True)
    
    print("\n📡 Downloading HVD (High Value Datasets)...")
    for cap, name, code in HVD_DATASETS:
        zip_path = HVD_DIR / f"{code}_{cap}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 1000:
            print(f"  ✅ {name} (already downloaded)")
            continue
        
        print(f"  ⬇ {name}...")
        for fmt in ['csv_bd', 'csv_bdsc', 'px']:
            url = f"https://www.ine.es/jaxiT3/GeneraZipServlet?cap={cap}&nocab=1&f={fmt}&n=fichero.zip"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                resp = urllib.request.urlopen(req, timeout=60)
                data = resp.read()
                if len(data) > 1000:
                    fname = f"{code}_{cap}_{fmt}.zip"
                    fpath = HVD_DIR / fname
                    fpath.write_bytes(data)
                    print(f"    → {fmt}: {len(data)/1024:.0f} KB")
                    break  # Got a valid download, move to next
            except:
                continue
    
    # Create OKF for HVD catalog
    hvd_lines = [
        "---",
        'okf_version: "1.0.0"',
        'title: "INE - Datos de Alto Valor (HVD)"',
        'description: "17 datasets de alto valor según Reglamento UE 2023/138. Descarga directa en CSV, PC-Axis y XLSX."',
        'source: "INE"',
        'type: "collection"',
        f'datasets: {len(HVD_DATASETS)}',
        f'scraped_at: "{datetime.now(timezone.utc).isoformat()}"',
        'tags: ["INE", "HVD", "datos de alto valor", "UE 2023/138"]',
        "---",
        "",
        "# INE - Datos de Alto Valor (HVD)",
        "",
        "## Datasets disponibles\n",
    ]
    for cap, name, code in HVD_DATASETS:
        hvd_lines.append(f'- **{name}** ({code}) — `c={cap}`')
    
    (OKF_DIR / "hvd_catalog.md").write_text('\n'.join(hvd_lines))
    print(f"  ✅ HVD catalog saved")

def create_okf_dataset(op, tables, total_series, total_values):
    """Create OKF bundle for an operation dataset"""
    op_id = op.get('Id', '')
    op_name = op.get('Nombre', 'Sin nombre')
    op_code = op.get('Codigo', '')
    
    # Determine tags
    tags = ['INE', 'economía española', 'datos abiertos']
    name_lower = op_name.lower()
    for kw in ['precio', 'pib', 'empleo', 'población', 'industria', 'comercio', 
               'turismo', 'vivienda', 'salario', 'consumo', 'contabilidad']:
        if kw in name_lower:
            tags.append(kw)
    
    okf_content = f"""---
okf_version: "1.0.0"
title: "{op_name}"
description: "Operación estadística del INE: {op_name}. {len(tables)} tablas disponibles con {total_series} series y {total_values} valores."
source: "INE"
type: "dataset"
operation_id: {op_id}
operation_code: "{op_code}"
tables_count: {len(tables)}
series_count: {total_series}
values_count: {total_values}
tags: {json.dumps(tags)}
license: "CC BY-SA 4.0"
url: "https://www.ine.es/dyngs/DAB/index.htm?cid=1722"
api_endpoint: "https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/{op_id}"
scraped_at: "{datetime.now(timezone.utc).isoformat()}"
okf_concept: "ine/datasets/{op_code.lower() if op_code else op_id}"
---

# {op_name}

## Descripción

Operación estadística del INE con código **{op_code}**.

## Tablas disponibles ({len(tables)})

"""
    for t in tables:
        tname = t.get('Nombre', '???')
        tid = t.get('Id', '')
        okf_content += f"- [{tname}](https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{tid}) (id={tid})\n"
    
    okf_content += f"""

## Acceso API

**Endpoint REST:** `https://servicios.ine.es/wstempus/js/ES/TABLAS_OPERACION/{op_id}`

**Datos:** `https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{{table_id}}`

**Formato:** JSON. Fechas en timestamp Unix (ms). Periodo = número de mes.
"""
    
    okf_path = CONCEPTOS_DIR / f"{op_code.lower() if op_code else f'op{op_id}'}.md"
    okf_path.write_text(okf_content)

def build_catalog_index(ops_data):
    """Build the master INE catalog index"""
    lines = [
        "---",
        'okf_version: "1.0.0"',
        'title: "INE - Catálogo de Datos Abiertos"',
        'description: "Repositorio OKF del Instituto Nacional de Estadística. 112 operaciones estadísticas, 461 publicaciones, acceso API JSON."',
        'source: "INE"',
        'type: "collection"',
        f'total_operations: {len(ops_data)}',
        f'scraped_at: "{datetime.now(timezone.utc).isoformat()}"',
        'tags: ["INE", "economía española", "datos abiertos", "API", "estadísticas"]',
        "---",
        "",
        "# INE - Catálogo de Datos Abiertos",
        "",
        "Fuente: [INE Datos Abiertos](https://www.ine.es/dyngs/DAB/index.htm?cid=1722)",
        f"Total operaciones: **{len(ops_data)}** | API: `https://servicios.ine.es/wstempus/js/ES/`",
        "",
        "## Operaciones Económicas",
    ]
    
    for op in ops_data:
        op_id = op.get('Id', '')
        op_name = op.get('Nombre', '')
        op_code = op.get('Codigo', '')
        if op_id in ECON_KEY_OPS:
            lines.append(f'\n### [{op_name}](conceptos/{op_code.lower() if op_code else f"op{op_id}"}.md)')
            lines.append(f'- **Código:** {op_code} | **ID:** {op_id}')
            lines.append(f'- **API:** `TABLAS_OPERACION/{op_id}`')
    
    lines.append("\n## Todas las Operaciones\n")
    for op in ops_data:
        op_name = op.get('Nombre', '')
        op_code = op.get('Codigo', '')
        op_id = op.get('Id', '')
        lines.append(f'- [{op_code}](conceptos/{op_code.lower() if op_code else f"op{op_id}"}.md) — {op_name[:80]}')
    
    (OKF_DIR / "index.md").write_text('\n'.join(lines))

def main():
    print("=" * 60)
    print("INE DATA AGENT — API JSON Extraction")
    print("=" * 60)
    
    # Phase 1: Get all operations
    all_ops = fetch_all_operations()
    
    # Phase 2: Get all publications
    pubs = fetch_publications()
    
    # Phase 3: For economics operations, fetch tables and data
    print("\n📊 Fetching tables and data for key operations...")
    total_tables = 0
    total_series = 0
    total_values = 0
    
    for op in all_ops:
        op_id = op.get('Id')
        if op_id not in ECON_KEY_OPS:
            continue
        
        op_code = op.get('Codigo', '')
        op_name = op.get('Nombre', f'Op {op_id}')
        print(f"\n  🔍 [{op_code}] {op_name[:60]}")
        
        tables = fetch_tables_for_operation(op_id, op_name)
        total_tables += len(tables)
        
        op_series = 0
        op_values = 0
        
        # Fetch data for up to 10 most important tables per operation
        for table in tables[:10]:
            tid = table.get('Id')
            tname = table.get('Nombre', '')
            series, vals = fetch_table_data(tid, tname, op_id)
            op_series += len(series)
            op_values += vals
            time.sleep(0.5)  # rate limit
        
        total_series += op_series
        total_values += op_values
        
        # Create OKF bundle for this operation
        create_okf_dataset(op, tables[:10], op_series, op_values)
        
        time.sleep(1)
    
    # Phase 3.5: Download HVD (High Value Datasets)
    download_hvd()
    
    # Phase 4: Build catalog
    print("\n📝 Building catalog...")
    build_catalog_index(all_ops)
    
    # Log
    log = f"""---
okf_version: "1.0.0"
title: "INE - Registro de cambios"
---
# Registro
| Fecha | Acción | Detalle |
|---|---|---|
| {datetime.now().strftime('%Y-%m-%d %H:%M')} | Extracción inicial | {len(all_ops)} ops, {total_tables} tablas, {total_series} series, {total_values} valores |
"""
    (OKF_DIR / "log.md").write_text(log)
    
    print(f"\n{'='*60}")
    print(f"✅ INE AGENT COMPLETE!")
    print(f"   Operations: {len(all_ops)}")
    print(f"   Key econ ops scraped: {len([o for o in all_ops if o.get('Id') in ECON_KEY_OPS])}")
    print(f"   Tables: {total_tables}")
    print(f"   Series (+values): {total_series} ({total_values})")
    print(f"   Location: {BASE_DIR}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
