# OKF Economía Española — Repositorio de Datos Abiertos

Repositorio estructurado en **formato OKF (Open Knowledge Format)** de datos y publicaciones económicas de España. Diseñado para que **agentes de IA** naveguen, consulten y crucen los datos sin necesidad de RAG ni bases de datos vectoriales.

## 🚀 Inicio rápido

```bash
# 1. Clonar
git clone https://github.com/Carlos-droid/Datos_estadisticos.git
cd Datos_estadisticos

# 2. Configurar ruta (opcional — por defecto /mnt/hdd/repositorio-okf-economia)
export OKF_BASE_DIR=$(pwd)
cp .env.example .env   # y editar si es necesario

# 3. Instalar dependencias
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 4. (Opcional) Instalar crawl4ai para scraping HTML
uv tool install crawl4ai

# 5. Ejecutar scraper
python3 src/python/scrape_ine.py       # INE (112 ops, 3.4M valores)
python3 src/python/scrape_funcas.py    # Funcas (930 docs)
python3 src/python/scrape_bbva.py      # BBVA Research (16 pubs)
```

## 📂 Estructura

```
OKF_BASE_DIR/
├── src/python/
│   ├── config.py          # Config portable (rutas, APIs, headers)
│   ├── log_utils.py       # Logging estructurado
│   ├── scrape_funcas.py   # Scraper Funcas
│   ├── scrape_bbva.py     # Scraper BBVA
│   ├── scrape_ine.py      # Scraper INE + HVD
│   ├── hooks/             # Hooks de seguridad (TODO)
│   └── reviewers/         # Revisores deterministas (TODO)
├── funcas/                # Documentos de trabajo (930)
│   ├── raw/               # Metadatos crudos + PDFs
│   ├── processed/         # Datos limpios (TODO)
│   └── okf/               # Bundles OKF para agentes
├── bbva/                  # Publicaciones BBVA Research (16)
│   └── okf/
├── ine/                   # Datos INE (112 ops, 3.4M valores)
│   ├── raw/
│   └── okf/
├── MANDATO.md             # Marco de desarrollo enterprise agentic
├── AGENTS.md              # Guía completa para agentes
├── PIPELINE.md            # Pipeline de actualizaciones
├── INTEGRACION.md         # Mapeo MANDATO → OKF
├── config.py              # → src/python/config.py
└── requirements.txt       # Dependencias
```

## 📊 Fuentes incluidas

| Fuente | Tipo | Docs/Datos |
|---|---|---|
| **Funcas** | Documentos de trabajo + notas técnicas | 930 docs (2007–2026) |
| **BBVA Research** | Publicaciones económicas | 16 informes |
| **INE API** | Operaciones estadísticas | 112 ops, 1.582 tablas, 3.4M valores |
| **INE HVD** | Datos de Alto Valor (UE 2023/138) | 17 datasets CSV |

## 🔄 Actualización programada

```bash
# Diario (Funcas)
python3 src/python/scrape_funcas.py

# Semanal (BBVA + INE)
python3 src/python/scrape_bbva.py
python3 src/python/scrape_ine.py
```

Los scrapers son **reanudables**: en cada ejecución solo procesan datos nuevos.

## 📜 Licencia

Apache-2.0. Datos del INE bajo CC BY-SA 4.0.
Atribución requerida para BBVA Research (ver términos en su web).
