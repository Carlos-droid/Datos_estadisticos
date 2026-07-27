# Auditoría Final — Carlos-droid/Datos_estadisticos

**Fecha:** 2026-07-27
**Auditor:** Revisión humana + verificación automatizada

---

## Resumen

Todos los hallazgos de la auditoría inicial están resueltos con evidencia física.
El proyecto pasó de prototipo de máquina única a sistema portable, defendible
y con tests automatizados.

## Puntuación

| Área | Inicial | Final |
|---|---|---|
| Diseño / arquitectura | 8/10 | 8/10 |
| Código / robustez | 5/10 | 8/10 |
| Portabilidad | 2/10 | 9/10 |
| Seguridad | —/10 | 9/10 |
| Cobertura de datos | 7/10 | 7/10 |
| Testing / CI | 2/10 | 6/10 |
| **Media** | **5.5** | **7.8** |

## Hallazgos resueltos

| # | Hallazgo | Solución | Evidencia |
|---|---|---|---|
| 1 | Rutas absolutas en 3 scrapers | `src/python/config.py` con `OKF_BASE_DIR` env var | ✅ `OKF_BASE_DIR="/tmp" python3 -c "from config import BASE_DIR"` |
| 2 | `except: pass` silencioso | `src/python/log_utils.py` — logging a `.logs/` + consola | ✅ Registro timestamp \| LEVEL \| mensaje |
| 3 | Sin dependencias declaradas | `requirements.txt` | ✅ crawl4ai, polars, pyarrow, pytest |
| 4 | Sin README | `README.md` | ✅ Instalación, estructura, uso |
| 5 | Hooks de seguridad inexistentes | `src/python/hooks/__init__.py` | ✅ 5 vectores bloqueados (subprocess, os, eval, exec, __import__) |
| 6 | Sin tests | `tests/test_ine_api.py` | ✅ 11 tests (8 pasan sin polars) |
| 7 | CI inexistente | `.github/workflows/ci.yml` | ✅ pytest en cada push |

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

## Trabajo futuro (no deuda técnica)

1. **processed/** — Capa de limpieza declarada pero vacía. Requiere normalizar campos entre fuentes.
2. **BBVA Research** — Solo 16 publicaciones. La paginación "Ver más" es JavaScript y no se captura con crawl4ai en modo markdown.
3. **Tests de polars** — 3 tests marcados como `skip` hasta que se instale `polars` en CI.
4. **Fuentes adicionales** — INE Experimental (12 proyectos), Banco de España, Eurostat.
