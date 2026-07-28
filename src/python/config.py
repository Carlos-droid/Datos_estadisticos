"""Configuración portable del Repositorio OKF de Economía Española.

Todas las rutas se resuelven desde OKF_BASE_DIR (variable de entorno)
o usan el valor por defecto. Esto hace el proyecto portable entre máquinas.
"""
import os
from pathlib import Path

# Raíz del repositorio — configurable vía entorno
BASE_DIR = Path(os.environ.get(
    "OKF_BASE_DIR",
    "/mnt/hdd/repositorio-okf-economia"
)).resolve()

# Directorios por fuente
FUNCAS_DIR  = BASE_DIR / "funcas"
BBVA_DIR    = BASE_DIR / "bbva"
INE_DIR     = BASE_DIR / "ine"

# Subdirectorios comunes
def source_dirs(base: Path) -> dict:
    return {
        "raw":        base / "raw",
        "raw_pdfs":   base / "raw" / "pdfs",
        "raw_hvd":    base / "raw" / "hvd",
        "processed":  base / "processed",
        "okf":        base / "okf",
        "conceptos":  base / "okf" / "conceptos",
    }

# Checkpoints
CHECKPOINTS_DIR = BASE_DIR / ".checkpoints"

# Logs
LOGS_DIR = BASE_DIR / ".logs"

# Crear estructura al importar
for d in [CHECKPOINTS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# APIs externas
INE_API_BASE = "https://servicios.ine.es/wstempus/js/ES"
FUNCAS_SITEMAP = "https://www.funcas.es/wp-sitemap-posts-documentos_trabajo-1.xml"
FUNCAS_LISTING = "https://www.funcas.es/publicaciones/documentos-de-trabajo-y-notas-tecnicas/listado-de-documentos-de-trabajo-y-notas-tecnicas/"

BBVA_SOURCES = [
    ("https://www.bbvaresearch.com/big-data/publicaciones/", "Big Data Publications"),
    ("https://www.bbvaresearch.com/geography/espana/",      "Spain Publications"),
    ("https://www.bbvaresearch.com/tag/big-data/",          "Big Data Tag"),
]

# ECB SDMX API (Statistical Data Warehouse)
ECB_API_BASE = "https://data-api.ecb.europa.eu/service"
ECB_DATAFLOWS = {
    "EXR": "Exchange Rates (tipos de cambio)",
    "ICP": "Harmonised Index of Consumer Prices (HICP/IPCA)",
    "MIR": "MFI Interest Rates (tipos de interés bancarios)",
    "BSI": "Balance Sheet Items (balances financieros)",
    "BOP": "Balance of Payments (balanza de pagos)",
    "FM":  "Financial Market (mercados financieros)",
    "STS": "Short-Term Statistics (estadísticas coyunturales)",
}
ECB_REF_AREA_ES = "ES"  # Código SDMX para España

# Directorio ECB
ECB_DIR = BASE_DIR / "ecb"

# User-Agent para peticiones HTTP
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
