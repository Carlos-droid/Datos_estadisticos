#!/usr/bin/env python3
"""Scraper ECB SDMX v2 — descarga datos macro en lotes.

Estrategia: UNA petición por dataflow con lastNObservations.
Filtra por España cuando el dataflow lo soporta.

Dataflows con España (ES): ICP, MIR, BSI, STS
Dataflows globales:         EXR (EUR denominator), BOP (euro area), FM (euro area)
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_repo_root = _this_dir.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.python.config import BASE_DIR, ECB_API_BASE, ECB_DIR, HTTP_HEADERS
from src.python.log_utils import ScrapeLogger

log = ScrapeLogger("ecb", "ECB")
RAW_ECB_DIR = ECB_DIR / "raw"
RAW_ECB_DIR.mkdir(parents=True, exist_ok=True)

LAST_N = 12

# Cada dataflow: path de series key (SDMX), label y si tiene España
DATAFLOWS = {
    # España individual
    "ICP": {"path": "/ICP/M.ES....",   "label": "HICP inflation Spain",       "has_es": True},
    "MIR": {"path": "/MIR/M.ES........","label": "MFI interest rates Spain",   "has_es": True},
    "BSI": {"path": "/BSI/M.ES.........",
             "label": "Balance sheet items Spain", "has_es": True},
    "STS": {"path": "/STS/M.ES.....",   "label": "Short-term stats Spain",    "has_es": True},
    # Contexto global
    "EXR": {"path": "/EXR/M..EUR..",    "label": "Exchange rates (EUR vs world)", "has_es": False},
    "BOP": {"path": "/BOP",             "label": "Balance of payments (euro area)", "has_es": False},
    "FM":  {"path": "/FM/M.U2.....",   "label": "Financial markets (euro area)", "has_es": False},
}

# Para BOP, no podemos filtrar por ES. Descargamos completo.
BOP_FULL = True  # Se maneja como caso especial


def _fetch_json(url: str) -> dict | None:
    req = urllib.request.Request(
        url, headers={**HTTP_HEADERS, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, OSError) as e:
        log.warning(f"HTTP error", url=url[:120], error=str(e))
        return None


def _extract_dim_name(dims: list[dict], code: str, dim_id: str) -> str:
    for dim in dims:
        if dim["id"] == dim_id:
            for v in dim.get("values", []):
                if v["id"] == code:
                    return v.get("name", code)
    return code


def _build_series_dict(sk: str, dims: list[dict],
                       observations: dict, time_values: list[str],
                       flow: str) -> dict:
    keys = sk.split(":")
    dim_codes = []
    dim_map = {}
    for i, k in enumerate(keys):
        idx = int(k)
        dim = dims[i] if i < len(dims) else {"id": f"dim{i}", "values": []}
        vals = dim.get("values", [])
        code = vals[idx]["id"] if idx < len(vals) else f"idx{idx}"
        dim_codes.append(code)
        dim_map[dim["id"]] = code

    dim_names = []
    for i, (dim, code) in enumerate(zip(dims, dim_codes)):
        name = _extract_dim_name(dims, code, dim["id"])
        dim_names.append(f"{dim['id']}={name}")

    obs_list = []
    for period_key, obs in sorted(observations.items(), key=lambda x: int(x[0])):
        period_idx = int(period_key)
        period = time_values[period_idx] if period_idx < len(time_values) else period_key
        obs_list.append({"period": period, "value": obs[0] if len(obs) > 0 else None})

    return {
        "flow": flow,
        "dim_codes": dim_codes,
        "dimensions": dim_map,
        "dimension_names": dim_names,
        "name": " | ".join(dim_names),
        "observations": obs_list,
        "last_value": obs_list[-1]["value"] if obs_list else None,
        "count": len(obs_list),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_flow(flow: str, path: str, label: str, has_es: bool) -> int:
    if flow == "BOP":
        return scrape_bop()

    url = f"{ECB_API_BASE}/data{path}?format=jsondata&lastNObservations={LAST_N}"
    log.info(f"=== {label} ===")
    log.info(f"GET {url[:120]}...")

    data = _fetch_json(url)
    if not data:
        return 0

    struct = data.get("structure", {})
    dims = struct.get("dimensions", {}).get("series", [])
    time_dim = struct.get("dimensions", {}).get("observation", [])
    time_values = []
    for td in time_dim:
        if td["id"] == "TIME_PERIOD":
            time_values = [v.get("name", v["id"]) for v in td.get("values", [])]

    all_series = []
    for ds in data.get("dataSets", []):
        for sk, sv in ds.get("series", {}).items():
            obs = sv.get("observations", {})
            if not obs:
                continue
            s = _build_series_dict(sk, dims, obs, time_values, flow)
            # Verificar que REF_AREA sea ES cuando el dataflow lo soporta
            if has_es and s["dimensions"].get("REF_AREA") != "ES":
                continue
            all_series.append(s)

    all_series.sort(key=lambda s: s["name"])

    out_path = RAW_ECB_DIR / f"{flow}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "flow": flow, "label": label, "has_es": has_es,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_series": len(all_series),
            "series": all_series,
        }, f, ensure_ascii=False, indent=2)

    log.info(f"  → {len(all_series)} series en {out_path}")
    return len(all_series)


def scrape_bop() -> int:
    """BOP: descarga completo y filtra áreas que incluyen España."""
    log.info("=== Balance of payments (euro area) ===")

    url = f"{ECB_API_BASE}/data/BOP/M.U2......?format=jsondata&lastNObservations={LAST_N}"
    data = _fetch_json(url)
    if not data:
        # Fallback: full download
        log.info("BOP: fallback a descarga completa...")
        url = f"{ECB_API_BASE}/data/BOP?format=jsondata&lastNObservations={LAST_N}"
        data = _fetch_json(url)
        if not data:
            return 0

    struct = data.get("structure", {})
    dims = struct.get("dimensions", {}).get("series", [])
    time_dim = struct.get("dimensions", {}).get("observation", [])
    time_values = []
    for td in time_dim:
        if td["id"] == "TIME_PERIOD":
            time_values = [v.get("name", v["id"]) for v in td.get("values", [])]

    all_series = []
    for ds in data.get("dataSets", []):
        for sk, sv in ds.get("series", {}).items():
            obs = sv.get("observations", {})
            if not obs:
                continue
            s = _build_series_dict(sk, dims, obs, time_values, "BOP")
            all_series.append(s)

    all_series.sort(key=lambda s: s["name"])

    out_path = RAW_ECB_DIR / "BOP.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "flow": "BOP", "label": "Balance of payments (euro area)",
            "has_es": False, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_series": len(all_series),
            "series": all_series,
        }, f, ensure_ascii=False, indent=2)

    log.info(f"  → {len(all_series)} series en {out_path}")
    return len(all_series)


def main():
    log.info("=== Scraper ECB SDMX v2 ===")
    total = 0

    for flow, cfg in DATAFLOWS.items():
        try:
            n = scrape_flow(flow, cfg["path"], cfg["label"], cfg["has_es"])
            total += n
        except Exception as e:
            log.error(f"{flow}: error", exc_info=True)

    log.info(f"✅ Total: {total} series de {len(DATAFLOWS)} dataflows")
    return total


if __name__ == "__main__":
    main()
