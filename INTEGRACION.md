# Cómo encaja el OKF Repository en el Marco MANDATO.md

## 1. Mapeo Directorio → Directorio

| MANDATO.md (Framework) | OKF Repository (Implementado) | Estado |
|---|---|---|
| `data/` (DVC) | `/mnt/hdd/repositorio-okf-economia/` | ✅ HDD local |
| `scratch/` | N/A (aún no hay cruces) | 📌 Pendiente |
| `src/python/agents/` → `graph.py` | `scrape_funcas.py`, `_bbva.py`, `_ine.py` | ✅ Scrapers deterministas |
| `src/python/hooks/security_hooks.py` | No implementado (scrapers sin código generado) | 📌 Pendiente |
| `src/python/reviewers/fanout_reviewer.py` | No implementado | 📌 Pendiente |
| `src/R/` | No implementado | 📌 Pendiente |
| `schemas/canonical_types.yaml` | `AGENTS.md` + `PIPELINE.md` (documentación) | 📌 Formalizar |
| `specs/open-spec/` | No implementado | 📌 Pendiente |
| `workflows/` (YAML) | `PIPELINE.md` | 📌 Formalizar |
| `tests/` | No implementado | 📌 Pendiente |

## 2. Lo que YA CUMPLIMOS del MANDATO

### ✅ Spec-First
Los scrapers existentes (`scrape_funcas.py`, `scrape_ine.py`) son **deterministas puros** — no generan código, ejecutan código conocido. Esto es equivalente a T-Shirt S (Tier 3).

### ✅ Reanudabilidad (Resumable)
El scraper INE tiene checkpoints que permiten reanudar. Esto satisface el principio de *incrementalidad* del MANDATO.

### ✅ Provenance
Cada documento OKF tiene `scraped_at`, `url`, `source` — trazabilidad completa hasta el origen.

### ✅ FS-Jail conceptual
Los scrapers solo escriben dentro de `/mnt/hdd/repositorio-okf-economia/` — el HDD actúa como jail natural.

### ✅ Formato ETL
`raw/` → `processed/` → `okf/` sigue el patrón de transformación en capas.

## 3. Lo que HAY QUE IMPLEMENTAR

### 🔲 Hooks de Seguridad
Cuando un agente genere código de cruce de datos (vs. scrapers fijos), necesitamos:
- `secure_fs_jail()` → confinar a `scratch/{run_id}/`
- `hook_no_net_python()` → AST check para bloquear red/sistema
- `secure_hmac_hash()` → anonimización de PII

### 🔲 Revisor de Fanout
Para cruces entre datasets (ej. cruzar IPC del INE con documentos de Funcas por año/tema):
```python
reviewer_fanout_leak(df_funcas, df_ipc, df_result, ["year"], "1:N")
```

### 🔲 Auto-Sizer + Three-Tier Routing
Cuando el agente reciba una petición de cruce:
1. **Auto-Sizer** clasifica S/M/L
2. **Router** elige modelo (Tier 1/2/3)
3. **Spec** requerida antes de tocar datos

### 🔲 Bucle `/retro`
Después de cada cruce complejo, extraer reglas → `learnings.md` → futuros cruces S.

### 🔲 Tests
- Tests unitarios para hooks y reviewers
- Tests de contrato para schemas
- Tests e2e nocturnos con subsets

## 4. Integración Inmediata

### Paso 1: Crear estructura faltante
```bash
mkdir -p /mnt/hdd/repositorio-okf-economia/{scratch,src/{python/{agents,hooks,reviewers,pipelines},R,bridge},schemas,specs/open-spec,workflows,tests,config}
```

### Paso 2: hooks/security_hooks.py y reviewers/fanout_reviewer.py
Copiar el código del MANDATO.md a esos archivos.

### Paso 3: Auto-Sizer como entry point
```python
def auto_sizer(desc: str, rows: int, has_pii: bool) -> str:
    if rows < 100_000 and not has_pii and "id=" in desc:
        return "S"  # Tier 3
    if "semantic" in desc.lower() or "fuzzy" in desc.lower():
        return "L"  # Tier 1 + humano
    return "M"  # Tier 2
```

## 5. Resumen

El OKF Repository es la **capa de datos** del sistema. El MANDATO.md es el **cerebro** que orquesta cómo se cruzan esos datos. Juntos forman:

```
MANDATO.md (Framework)
    ↓
Auto-Sizer → Router (Tier 1/2/3) → Spec
    ↓
OKF Repository (Datos: Funcas, BBVA, INE)
    ↓
Hooks (Seguridad) → Engineer Node → QA Node (Fanout Reviewer)
    ↓
Resultado → /retro → learnings.md
```
