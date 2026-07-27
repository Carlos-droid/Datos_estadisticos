# AGENTS.md — Repositorio OKF de Economía Española

## 📋 Índice

1. [Arquitectura del Sistema](#1-arquitectura-del-sistema)
2. [Alcance y Fuentes](#2-alcance-y-fuentes)
3. [Formato OKF](#3-formato-okf)
4. [Pipeline de Datos](#4-pipeline-de-datos)
5. [Observabilidad](#5-observabilidad)
6. [Trazabilidad](#6-trazabilidad)
7. [Guía para Agentes](#7-guía-para-agentes)
8. [Operaciones](#8-operaciones)

---

## 1. Arquitectura del Sistema

### 1.1 Visión general

```
┌─────────────────────────────────────────────────────────────────────┐
│                    REPOSITORIO OKF ECONOMÍA ESPAÑOLA                │
│                    /mnt/hdd/repositorio-okf-economia/               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │  FUNCAS  │  │   BBVA   │  │   INE    │  │  EXPERIMENTALES  │   │
│  │          │  │ Research │  │          │  │  (futuro)         │   │
│  │  930 doc │  │  16 pub  │  │ 112 ops  │  │  IPVA, VIME,     │   │
│  │  70 PDFs │  │          │  │1582 tabs │  │  IMCV, movilidad │   │
│  │          │  │          │  │3.4M vals │  │  ...             │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
│       │              │             │                  │            │
│       ▼              ▼             ▼                  ▼            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    CAPA DE ALMACENAMIENTO                    │  │
│  │                                                              │  │
│  │  raw/        → Datos crudos (JSONL, PDFs, ZIP)              │  │
│  │  processed/  → Datos limpios y normalizados (pendiente)     │  │
│  │  okf/        → Bundles OKF para agentes (index + conceptos) │  │
│  │  .checkpoints/ → Estado incremental para reanudación        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                          ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    CAPA DE CONSUMO                           │  │
│  │                                                              │  │
│  │  Agente de consulta → Catálogo OKF → Datos por fuente       │  │
│  │  Agente de análisis → Series temporales → Modelos ML        │  │
│  │  Agente de alertas → Monitor de cambios → Notificaciones    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Principios de diseño

1. **Inmutabilidad progresiva**: Los datos crudos (`raw/`) nunca se modifican. La limpieza genera nuevos archivos en `processed/`. Los OKF bundles se regeneran desde `processed/`.
2. **Incrementalidad**: Cada ejecución solo procesa datos nuevos. Los checkpoints guardan el progreso.
3. **Independencia por fuente**: Cada fuente tiene su propio scraper, checkpoint y pipeline. No hay dependencias cruzadas.
4. **Formato único de salida**: Todo converge a OKF (Markdown con YAML frontmatter) para que cualquier agente lo navegue.

### 1.3 Flujo de datos

```
Fuente externa
     │
     ▼
[Scraper determinista] ──→ raw/ (JSONL, binario)
     │                          │
     │                          ▼
     │                   [Limpieza] ──→ processed/ (JSONL normalizado)
     │                          │
     ▼                          ▼
[LLM local (opcional)] ──→ okf/ (Markdown + YAML)
     │
     ▼
Catálogo index.md ──→ Agentes de consumo
```

---

## 2. Alcance y Fuentes

### 2.1 Funcas — Documentos de Trabajo y Notas Técnicas (2007–2026)

| Propiedad | Valor |
|---|---|
| **URL origen** | `https://www.funcas.es/publicaciones/documentos-de-trabajo-y-notas-tecnicas/` |
| **Sitemap** | `https://www.funcas.es/wp-sitemap-posts-documentos_trabajo-1.xml` |
| **Total documentos** | 930 |
| **OKF bundles** | 926 |
| **PDFs descargados** | 70 |
| **URL patrón** | `https://www.funcas.es/documentos_trabajo/<slug>/` |
| **Actualización** | Diaria (cron), vía diff de sitemap.lastmod |
| **Scraper** | `scrape_funcas.py` |

Campos extraídos por documento:
- `id`, `url`, `lastmod`, `title`, `author_raw`, `date`, `pdf_url`, `abstract`

### 2.2 BBVA Research — Publicaciones

| Propiedad | Valor |
|---|---|
| **URL origen** | `https://www.bbvaresearch.com/big-data/publicaciones/` |
| **URLs adicionales** | `/geography/espana/`, `/tag/big-data/`, `/publicaciones/` |
| **Total publicaciones** | 16 |
| **OKF bundles** | 15 |
| **Actualización** | Semanal (cron), vía diff de títulos |
| **Scraper** | `scrape_bbva.py` |

Campos extraídos:
- `title`, `url`, `geography` (España|Global|México...), `technique` (big-data|null), `date_raw`, `source_url`

### 2.3 INE — API REST + HVD

| Propiedad | Valor |
|---|---|
| **API base** | `https://servicios.ine.es/wstempus/js/ES/` |
| **Endpoint HVD** | `https://www.ine.es/jaxiT3/GeneraZipServlet?cap={id}&f=csv_bd` |
| **Total operaciones** | 112 |
| **Operaciones económicas** | 25 (IPC, EPA, IPI, IPCA, CNTR, IPV, IPRI, IPH, ICM, ICN, EI, IPS, IPRX-M, ICES, ETR, VTE, TMOV, IPAP, IPAC, IPTR, IPT, MOS, STEC, IPVA) |
| **Tablas extraídas** | 1.582 |
| **Series temporales** | 106.161 |
| **Valores numéricos** | 3.466.305 |
| **Publicaciones INE** | 461 |
| **HVD datasets** | 17 |
| **Actualización** | Semanal (cron), vía diff de operaciones/tablas |
| **Scraper** | `scrape_ine.py` |

**API pública, sin autenticación.** Formato JSON con timestamps Unix (ms). Los HVD incluyen datos de PIB, población, pobreza, desigualdad, IPI, IPRI, IPCA, turismo, etc.

### 2.4 Fuentes futuras (pendientes)

| Fuente | Estado | Prioridad |
|---|---|---|
| INE Experimental (IPVA, VIME, IMCV, movilidad, turismo móviles, viviendas turísticas) | 🔜 Encolado | Alta |
| Banco de España — Documentos de trabajo | 📋 Pendiente | Media |
| Eurostat — Datos España vía SDMX | 📋 Pendiente | Media |
| Ayudas públicas (ayudas públicas español AI) | 📋 Pendiente | Baja |

---

## 3. Formato OKF

### 3.1 Estructura de un bundle

Cada fuente sigue esta estructura:

```
fuente/okf/
├── index.md        → Catálogo maestro (YAML frontmatter + enlaces)
├── log.md          → Registro de cambios (tabla cronológica)
└── conceptos/      → Un .md por documento/dataset
    ├── doc-001.md
    ├── doc-002.md
    └── ...
```

### 3.2 Frontmatter YAML estándar

**Para documentos (Funcas/BBVA):**
```yaml
---
okf_version: "1.0.0"
title: "Título del documento"
description: "Resumen o abstract"
source: "Funcas" | "BBVA Research"
type: "documento_trabajo" | "nota_tecnica" | "investigacion" | "informe"
authors: ["Autor1", "Autor2"]
date: "2026-07"
published: "2026-07-24T09:10:02+00:00"
lang: "es"
url: "https://..."
pdf_url: "https://..."
pdf_path: "/mnt/hdd/...pdf"
tags: ["economía", "españa", "funcas"]
scraped_at: "2026-07-26T22:30:00+00:00"
okf_concept: "funcas/documents/slug"
---
```

**Para datasets (INE):**
```yaml
---
okf_version: "1.0.0"
title: "IPC - Índice general nacional"
source: "INE"
type: "dataset"
operation_id: 25
operation_code: "IPC"
tables_count: 59
series_count: 500
values_count: 95000000
tags: ["INE", "IPC", "precios", "inflación"]
license: "CC BY-SA 4.0"
api_endpoint: "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/24077"
scraped_at: "2026-07-26T..."
okf_concept: "ine/datasets/ipc"
---
```

### 3.3 Progresión de disclosure

Los OKF bundles siguen el principio de **progressive disclosure**:
1. `index.md` → visión general, estadísticas, enlaces
2. Listado en index.md → título + breve descripción
3. Concepto individual → frontmatter completo + cuerpo markdown
4. Datos crudos en raw/ → JSONL, CSV, ZIP a los que el concepto enlaza

---

## 4. Pipeline de Datos

### 4.1 Estrategias por fuente

| Fuente | Estrategia | Gatillo | Script |
|---|---|---|---|
| Funcas | Determinista + LLM | Cron diario 6:00 | `scrape_funcas.py` |
| BBVA | Determinista | Cron semanal lunes 8:00 | `scrape_bbva.py` |
| INE API | Determinista | Cron semanal lunes 10:00 | `scrape_ine.py` |
| Experimentales | LLM local | Bajo demanda | `process_experimental.py` |

### 4.2 Checkpoints

Cada scraper escribe su progreso en `/mnt/hdd/repositorio-okf-economia/.checkpoints/`:

```
.checkpoints/
├── funcas_last.txt          → Último lastmod procesado del sitemap
├── bbva_last.txt            → Último título/URL procesado
├── ine_operations.json      → IDs de operaciones ya scrapeadas
└── ine_tables.json          → IDs de tablas ya descargadas
```

En cada ejecución:
1. Leer checkpoint
2. Fetch datos nuevos
3. Hacer diff contra checkpoint
4. Procesar solo lo nuevo
5. Actualizar checkpoint

### 4.3 Limpieza de datos (processed/)

Los datos en `processed/` son versiones normalizadas de `raw/`:
- JSONL con campos consistentes entre fuentes
- Fechas en ISO 8601
- Valores numéricos como float/int, no strings
- Texto sin HTML tags
- Encoding UTF-8 garantizado

**Campos comunes normalizados:**
```json
{
  "source": "funcas",
  "source_id": "competencias-basicas-...",
  "title": "...",
  "authors": ["..."],
  "date": "2026-07",
  "date_iso": "2026-07-24",
  "abstract": "...",
  "url": "...",
  "pdf_path": "...",
  "tags": ["economía", "españa"],
  "language": "es",
  "ingested_at": "2026-07-26T22:30:00Z"
}
```

---

## 5. Observabilidad

### 5.1 Métricas clave

Cada scraper reporta al finalizar:

| Métrica | Funcas | BBVA | INE |
|---|---|---|---|
| Documentos/operaciones | 930 | 16 | 112 |
| Tablas/datos nuevos | N/A | N/A | 1.582 |
| Valores numéricos | N/A | N/A | 3.4M |
| PDFs/descargas | 70 | 0 | 17 HVD |
| OKF bundles generados | 926 | 15 | 25+1 |
| Errores HTTP | 2 (404 PDF) | 0 | 2 (API string) |
| Duración | ~5 min | ~30s | ~8 min |

### 5.2 Puntos de observación

```
1. 📡 Fetch externo
   └── ¿Respuesta 200? ¿Timeout? ¿403?

2. 📝 Parseo
   └── ¿Coinciden los campos esperados? ¿Datos vacíos?

3. 💾 Escritura raw/
   └── ¿Archivo escrito? ¿Tamaño > 0?

4. 🧹 Limpieza (processed/)
   └── ¿Datos válidos? ¿Duplicados?

5. 📄 Generación OKF
   └── ¿YAML válido? ¿Campos obligatorios completos?
```

### 5.3 Alertas

El sistema debe generar alertas cuando:
- **404/403 recurrente** en fuente externa (página caída o bloqueada)
- **0 documentos nuevos** en ejecución programada (posible cambio de estructura)
- **Error de parseo** en más del 10% de documentos
- **Checkpoint no actualizado** después de ejecución exitosa
- **Disco por debajo de 10% libre** en /mnt/hdd

### 5.4 Logging

Cada scraper escribe logs en:
```
.funcas_last_run.log
.bbva_last_run.log
.ine_last_run.log
```

Contienen: timestamp, documentos procesados, errores, duración.

---

## 6. Trazabilidad

### 6.1 Línea de origen (Provenance)

Cada valor o documento en el repositorio puede trazarse hasta su origen:

```
Documento OKF
    │
    ├── source: "Funcas"
    ├── url: "https://www.funcas.es/documentos_trabajo/slug/"
    ├── lastmod: "2026-07-24T09:10:02+00:00"  (del sitemap)
    ├── scraped_at: "2026-07-26T22:30:00+00:00"
    └── pdf_url: "https://www.funcas.es/wp-content/uploads/..."
         │
         └── SHA256 del PDF: abc123... (para verificar integridad)

Valor estadístico INE
    │
    ├── source: "INE"
    ├── operation_id: 25 (IPC)
    ├── table_id: 24077 (Índice general nacional)
    ├── api_endpoint: "DATOS_TABLA/24077"
    ├── series_cod: "IPC290751"
    ├── anyo: 2026
    ├── periodo: 6
    ├── valor: 103.598
    └── scraped_at: "2026-07-26T22:30:00+00:00"
```

### 6.2 Cadena de transformación

```
Raw (JSONL línea 1) ──→ Clean (JSONL campo normalizado) ──→ OKF (YAML)
     ↑                       ↑                              ↑
  Fuente externa          Script limpieza                Script OKF
  Timestamp fetch         Timestamp clean                Timestamp generate
```

Cada transformación añade un campo `*_at` con timestamp y el script que la generó.

### 6.3 Detección de cambios

Para actualizaciones incrementales:
1. **Funcas**: Comparar `lastmod` del sitemap con `funcas_last.txt`
2. **BBVA**: Comparar títulos/URLs con los existentes en `raw/docs.jsonl`
3. **INE**: Comparar listado de tablas (`TABLAS_OPERACION`) con checkpoint

---

## 7. Guía para Agentes

### 7.1 Cómo navegar el repositorio

```
1. Empieza en:  /mnt/hdd/repositorio-okf-economia/
2. Lee:         PIPELINE.md (este documento) y AGENTS.md (este archivo)
3. Por fuente:  funcas/okf/index.md → catálogo Funcas
                bbva/okf/index.md   → catálogo BBVA
                ine/okf/index.md    → catálogo INE
4. Busca:       okf/conceptos/<slug>.md → detalle de un documento/dataset
5. Datos crudos: raw/ → JSONL con datos sin procesar
6. Datos limpios: processed/ → JSONL normalizado
```

### 7.2 Comandos útiles

```bash
# Contar documentos OKF
find /mnt/hdd/repositorio-okf-economia -name "conceptos" -exec ls {} \; | wc -l

# Buscar en todo el catálogo
grep -r "inflación" /mnt/hdd/repositorio-okf-economia/*/okf/conceptos/

# Ver tamaño por fuente
du -sh /mnt/hdd/repositorio-okf-economia/{funcas,bbva,ine}

# Ver progreso del scraper
tail -5 /mnt/hdd/repositorio-okf-economia/ine/*.log

# Consultar la API del INE directamente
curl -s "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/24077?date=2026-01-01:2026-07-01"
```

### 7.3 Cómo añadir una fuente nueva

1. Crear `scrape_nueva_fuente.py` siguiendo el patrón:
   - Fetch externo → raw/ (JSONL)
   - Limpieza → processed/ (JSONL normalizado)
   - Generación → okf/ (bundles)
   - Checkpoint → .checkpoints/

2. Añadir entrada en este `AGENTS.md` en [Alcance y Fuentes](#2-alcance-y-fuentes)

3. Añadir los campos de observabilidad en [Métricas clave](#51-métricas-clave)

4. Registrar en el log central: `echo "[$(date)] Nueva fuente: ..." >> ingestion.log`

### 7.4 Cómo ejecutar una actualización

```bash
# Manual
cd /mnt/hdd/repositorio-okf-economia
python3 scrape_funcas.py   # Solo datos nuevos (resume)
python3 scrape_bbva.py
python3 scrape_ine.py

# Programado (cron jobs)
hermes cron create \
  --name "okf-funcas-update" \
  --schedule "0 6 * * *" \
  --script /mnt/hdd/repositorio-okf-economia/scrape_funcas.py

hermes cron create \
  --name "okf-bbva-update" \
  --schedule "0 8 * * 1" \
  --script /mnt/hdd/repositorio-okf-economia/scrape_bbva.py

hermes cron create \
  --name "okf-ine-update" \
  --schedule "0 10 * * 1" \
  --script /mnt/hdd/repositorio-okf-economia/scrape_ine.py
```

---

## 8. Operaciones

### 8.1 Estructura de directorios completa

```
/mnt/hdd/repositorio-okf-economia/
├── AGENTS.md                    ← Este documento
├── PIPELINE.md                  ← Pipeline design
├── scrape_funcas.py             ← Scraper Funcas
├── scrape_bbva.py               ← Scraper BBVA
├── scrape_ine.py                ← Scraper INE + HVD
├── .checkpoints/                ← Estado incremental
│   ├── funcas_last.txt
│   ├── bbva_last.txt
│   ├── ine_operations.json
│   └── ine_tables.json
├── funcas/
│   ├── raw/
│   │   ├── docs.jsonl           ← 930 docs metadata
│   │   └── pdfs/                ← 70 PDF files
│   ├── processed/               ← (pendiente)
│   └── okf/
│       ├── index.md             ← Catálogo Funcas
│       ├── log.md               ← Change log
│       └── conceptos/           ← 926 OKF bundles
├── bbva/
│   ├── raw/docs.jsonl           ← 16 publications
│   ├── processed/               ← (pendiente)
│   └── okf/
│       ├── index.md             ← Catálogo BBVA
│       ├── log.md
│       └── conceptos/           ← 15 OKF bundles
└── ine/
    ├── raw/
    │   ├── operaciones.jsonl    ← 112 ops metadata
    │   ├── publicaciones.jsonl  ← 461 pubs metadata
    │   ├── tables_op*.jsonl     ← Table metadata per op
    │   ├── data_op*_t*.jsonl    ← ~150 data files
    │   └── hvd/*.zip            ← 17 HVD datasets
    ├── processed/               ← (pendiente)
    └── okf/
        ├── index.md             ← Catálogo INE maestro
        ├── hvd_catalog.md       ← Catálogo HVD
        ├── log.md
        └── conceptos/           ← 25+ OKF bundles
```

### 8.2 Dependencias del sistema

- **Python 3.11+** con urllib (stdlib), json (stdlib)
- **crawl4ai** (`uv tool install crawl4ai`) para scraping HTML
- **curl** para tests rápidos
- **396 GB libres** en `/mnt/hdd` (mínimo recomendado: 50 GB)

### 8.3 Límites conocidos

1. **Funcas PDFs**: Solo 70/930 PDFs descargados (muchos docs antiguos no tienen PDF público o el enlace es 404)
2. **BBVA**: Solo 16 publicaciones. La paginación "Ver más" es JS y no se captura. Los working papers históricos están sueltos en `/wp-content/uploads/` sin índice.
3. **INE API**: Algunas tablas devuelven strings de error en lugar de JSON array (manejado con skip). El IPCA y tablas grandes pueden tardar varios segundos.
4. **HVD**: Algunos datasets devuelven ZIPs muy pequeños (~1 KB) indicando que el formato solicitado no está disponible.

### 8.4 Próximos pasos

1. ✅ Scraping inicial completado
2. ⬜ Limpieza de datos (processed/)
3. ⬜ Implementar scripts de actualización incremental
4. ⬜ Configurar cron jobs
5. ⬜ Scraping de estadísticas experimentales del INE
6. ⬜ Banco de España
7. ⬜ Agente de consulta sobre el catálogo OKF
