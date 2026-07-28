# Auditoría — Carlos-droid/Datos_estadisticos

**Fecha:** 2026-07-28
**Auditor:** Revisión humana + verificación automatizada

---

## Resumen

El proyecto cruzó un umbral cualitativo: pasó de ser un repositorio de documentos económicos a un **sistema de datos económicos con búsqueda semántica**. La integración ECB SDMX añadió 3.243 series macro que ninguna de las tres fuentes originales cubría, y el agente puede ahora responder consultas conceptuales ("inflación hogares") sin que el usuario necesite conocer la estructura de los dataflows del BCE.

Dos indicadores de madurez técnica sólidos: embeddings en lote a 3.5 min (vs 35 min secuencial antes) y CI verde en dos runs consecutivos.

---

## Puntuación

| Área | Sesión anterior | Hoy |
|---|---|---|
| Diseño / arquitectura | 8/10 | 9/10 |
| Código / robustez | 8/10 | 8/10 |
| Portabilidad | 9/10 | 9/10 |
| Seguridad | 9/10 | 9/10 |
| Cobertura de datos | 7/10 | 9/10 |
| Testing / CI | 6/10 | 8/10 |
| Agente / utilidad | —/10 | 8/10 |
| **Media** | **7.8** | **8.6** |

### Desglose de cambios

**Cobertura de datos 7→9:** ECB SDMX añadió 7 dataflows (ICP, MIR, BSI, STS, EXR, BOP, FM) con 3.243 series temporales. El catálogo pasó de 1.052 a 4.295 ítems, y la nueva dimensión `time_series` cubre inflación armonizada, tipos de interés, balances financieros, tipos de cambio, balanza de pagos y mercados financieros — todo para España o área euro. Ninguna de las tres fuentes originales (Funcas, BBVA, INE) proporcionaba este tipo de datos.

**Testing/CI 6→8:** CI verde en dos ejecuciones consecutivas (#1 CI activation, #2 ECB+embeddings). Tests estructurales offline (14) cubren importabilidad, estructura del repo y validez del catálogo. El CI se ejecuta en cada push a `main`.

**Nueva dimensión Agente/utilidad 8/10:** El proyecto tiene un consumidor real de los datos — `agente_okf.py` con 5 herramientas (listar fuentes, búsqueda textual, búsqueda semántica, bundles OKF, API INE en tiempo real). La búsqueda semántica funciona sobre los 4.295 items con embeddings precomputados.

---

## Hallazgos resueltos (histórico)

| # | Hallazgo | Solución | Evidencia |
|---|---|---|---|
| 1 | Rutas absolutas en 3 scrapers | `src/python/config.py` con `OKF_BASE_DIR` env var | ✅ `OKF_BASE_DIR="/tmp" python3 -c "from config import BASE_DIR"` |
| 2 | `except: pass` silencioso | `src/python/log_utils.py` — logging a `.logs/` + consola | ✅ Registro timestamp \| LEVEL \| mensaje |
| 3 | Sin dependencias declaradas | `requirements.txt` | ✅ crawl4ai, polars, pyarrow, pytest |
| 4 | Sin README | `README.md` | ✅ Instalación, estructura, uso |
| 5 | Hooks de seguridad inexistentes | `src/python/hooks/__init__.py` | ✅ 5 vectores bloqueados (subprocess, os, eval, exec, __import__) |
| 6 | Sin tests | `tests/test_ine_api.py` + `tests/test_structure.py` | ✅ 25 tests (14 offline + 11 API/skip) |
| 7 | CI inexistente | `.github/workflows/ci.yml` | ✅ pytest en cada push |
| 8 | Sin datos macro europeos | `src/python/pipelines/ecb_scraper.py` + `normalize_ecb()` | ✅ 3.243 series ECB en catalog.jsonl |
| 9 | Embeddings secuenciales lentos | `embeddings.py` migrado a `/api/embed` con lotes de 50 | ✅ 4.295 items en 3.5 min (vs 35 min) |
| 10 | Sin modelo más ligero | `nomic-embed-text` (262 MB) en vez de v2-moe (913 MB) | ✅ Misma dimensión 768, más estable |

---

## Vectores de seguridad verificados

| Vector | Código | Bloqueado |
|---|---|---|
| subprocess | `import subprocess; subprocess.run(['ls'])` | ✅ |
| os.system | `import os; os.system('ls')` | ✅ |
| os via ImportFrom | `from os import system; system('ls')` | ✅ |
| eval | `eval('1+1')` | ✅ |
| exec | `exec('print(1)')` | ✅ |
| __import__ | `__import__('os').system('ls')` | ✅ |
| FS-Jail | `secure_fs_jail('/etc/passwd', 'run-001')` | ✅ |

---

## Trabajo futuro (ordenado por impacto)

1. **Cron de actualización ECB** — El scraper ya existe, solo falta un schedule (`every 6h` o diario). Sin él, los embeddings y el catálogo se desactualizan y el agente empieza a devolver datos obsoletos sin avisar.
2. **Eurostat** — Más datos macro UE (misma API SDMX, otros dataflows).
3. **Dashboard/visualización** — Solo tiene sentido si hay consumo externo del agente. El CLI es suficiente para uso personal.
4. **BBVA Research** — Solo 10 publicaciones. La paginación con JavaScript no se captura con crawl4ai en modo markdown.
5. **Tests de polars** — 3 tests marcados como `skip` hasta que se instale `polars` en CI.
