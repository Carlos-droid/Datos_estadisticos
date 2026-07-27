#!/usr/bin/env python3
"""
Agente de consulta OKF — Repositorio Economía Española
Herramientas adaptadas al esquema real de catalog.jsonl y bundles okf/

Esquema de catalog.jsonl:
  Campos comunes:  id, source, title, date_iso, description, tags, url, type, normalized_at
  Funcas:          authors, date_raw, pdf_url
  BBVA Research:   geography, technique, date_raw
  INE:             operation_id, operation_code, tables_count

Tipos reales en catálogo:
  - working_paper  (Funcas)
  - report         (BBVA Research, algunos Funcas)
  - dataset        (INE)

Uso:
  pip install openai python-dotenv
  export OPENROUTER_API_KEY=...   # o AGENTE_MODO=OLLAMA
  python agente_okf.py
"""

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# ---------------------------------------------------------------------------
# BACKEND OPCIONAL: solo falla si se intenta usar sin tener instalado openai
# ---------------------------------------------------------------------------
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # Se comprueba al conectar

# Cargar .env si existe (path relativo o desde OKF_BASE_DIR)
_env_loaded = False
def _ensure_dotenv():
    global _env_loaded
    if _env_loaded:
        return
    # Priorizar dotenv si está disponible
    if load_dotenv is not None:
        base = os.getenv("OKF_BASE_DIR", "/mnt/hdd/repositorio-okf-economia")
        for env_path in (Path(base) / ".env", Path.cwd() / ".env"):
            if env_path.exists():
                load_dotenv(str(env_path))
                break
    _env_loaded = True

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

_ensure_dotenv()  # Cargar .env antes de leer vars de entorno

MODO = os.getenv("AGENTE_MODO", "OPENROUTER")  # "OPENROUTER" | "OLLAMA"

def _conectar():
    if OpenAI is None:
        raise ImportError(
            "La librería 'openai' no está instalada.\n"
            "  pip install openai"
        )
    if MODO == "OPENROUTER":
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Agente OKF Economía Española",
            },
        )
        modelo = os.getenv("AGENTE_MODELO", "google/gemini-2.0-flash-001")
    elif MODO == "OLLAMA":
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )
        modelo = os.getenv("AGENTE_MODELO", "qwen2.5:7b")
    else:
        raise ValueError(f"AGENTE_MODO inválido: {MODO}. Usa OPENROUTER o OLLAMA.")
    return client, modelo

# Rutas del repositorio OKF
BASE_DIR = Path(os.getenv("OKF_BASE_DIR", "/mnt/hdd/repositorio-okf-economia"))
CATALOG_PATH = BASE_DIR / "processed" / "catalog.jsonl"
OKF_DIRS = {
    "funcas": BASE_DIR / "funcas" / "okf" / "conceptos",
    "bbva":   BASE_DIR / "bbva"   / "okf" / "conceptos",
    "ine":    BASE_DIR / "ine"    / "okf" / "conceptos",
}

# ---------------------------------------------------------------------------
# CARGA DEL CATÁLOGO (una vez, en memoria)
# ---------------------------------------------------------------------------

def _cargar_catalogo() -> list[dict]:
    """Carga catalog.jsonl en memoria. Falla limpio si no existe."""
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró catalog.jsonl en {CATALOG_PATH}. "
            "Ejecuta primero src/python/pipelines/normalize.py"
        )
    registros = []
    with open(CATALOG_PATH, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                registros.append(json.loads(linea))
    return registros

CATALOGO: list[dict] = []  # Se carga al primer uso
def _catalogo() -> list[dict]:
    global CATALOGO
    if not CATALOGO:
        CATALOGO = _cargar_catalogo()
    return CATALOGO


# ---------------------------------------------------------------------------
# HERRAMIENTA 1 — listar_fuentes
# ---------------------------------------------------------------------------

def listar_fuentes() -> str:
    """
    Devuelve un resumen del catálogo: cuántos ítems por fuente,
    tipos disponibles, rango temporal y total de ítems.
    Equivale a leer index.md — punto de entrada del agente.
    """
    cat = _catalogo()
    total = len(cat)

    por_fuente: dict[str, int] = {}
    for r in cat:
        src = r.get("source", "desconocido")
        por_fuente[src] = por_fuente.get(src, 0) + 1

    tipos: set[str] = {r.get("type", "") for r in cat if r.get("type")}

    fechas = [r["date_iso"] for r in cat if r.get("date_iso")]
    fecha_min = min(fechas) if fechas else "desconocida"
    fecha_max = max(fechas) if fechas else "desconocida"

    conteo_tags: dict[str, int] = {}
    for r in cat:
        for tag in r.get("tags", []):
            conteo_tags[tag] = conteo_tags.get(tag, 0) + 1
    top_tags = sorted(conteo_tags, key=conteo_tags.get, reverse=True)[:10]

    resumen = {
        "total_items": total,
        "por_fuente": por_fuente,
        "tipos_disponibles": sorted(tipos),
        "rango_temporal": {"desde": fecha_min, "hasta": fecha_max},
        "tags_mas_frecuentes": top_tags,
        "campos_disponibles": [
            "id", "source", "title", "date_iso", "description",
            "tags", "url", "type", "normalized_at",
            "authors", "date_raw", "pdf_url",                # Funcas
            "geography", "technique", "date_raw",            # BBVA
            "operation_id", "operation_code", "tables_count", # INE
        ],
    }
    return json.dumps(resumen, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# HERRAMIENTA 2 — buscar_en_catalogo
# ---------------------------------------------------------------------------

def buscar_en_catalogo(
    source: str | None = None,
    tipo: str | None = None,
    type: str | None = None,   # alias inglés
    desde: str | None = None,
    hasta: str | None = None,
    texto: str | None = None,
    tags: list[str] | None = None,
    geography: str | None = None,
    max_resultados: int = 20,
) -> str:
    """
    Filtra catalog.jsonl con criterios combinables. Todos los parámetros
    son opcionales y se aplican en AND.
    """
    cat = _catalogo()
    resultados = []
    texto_lower = texto.lower() if texto else None
    # Normalizar acentos para búsqueda (ej. "inflación" → "inflacion")
    texto_plain = _strip_accents(texto_lower) if texto_lower else None
    # Aceptar tanto 'tipo' como 'type' (alias inglés)
    filtro_tipo = tipo or type

    for r in cat:
        # Source match flexible: "bbva" → "BBVA Research", "ine" → "INE", "funcas" → "Funcas"
        if source:
            r_source = r.get("source", "").lower()
            s_lower = source.lower()
            if r_source != s_lower and s_lower not in r_source and r_source not in s_lower:
                continue
        if filtro_tipo and r.get("type", "").lower() != filtro_tipo.lower():
            continue
        if desde and (r.get("date_iso") or "") < desde:
            continue
        if hasta and (r.get("date_iso") or "") > hasta:
            continue
        # Filtro texto libre (insensible a acentos)
        if texto_lower:
            haystack = (
                (r.get("title") or "").lower()
                + " "
                + (r.get("description") or "").lower()
            )
            haystack_plain = _strip_accents(haystack)
            if texto_lower not in haystack and texto_plain not in haystack_plain:
                continue
        if tags:
            r_tags = [t.lower() for t in r.get("tags", [])]
            if not all(t.lower() in r_tags for t in tags):
                continue
        if geography and r.get("geography", "").lower() != geography.lower():
            continue

        resultados.append({
            "id":          r.get("id"),
            "source":      r.get("source"),
            "title":       r.get("title"),
            "date_iso":    r.get("date_iso"),
            "description": (r.get("description") or "")[:200],
            "url":         r.get("url"),
            "tags":        r.get("tags", []),
            "type":        r.get("type"),
        })

    total_encontrados = len(resultados)
    recortados = resultados[:max_resultados]

    return json.dumps(
        {
            "total_encontrados": total_encontrados,
            "mostrando": len(recortados),
            "resultados": recortados,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# HERRAMIENTA 3 — leer_bundle_okf
# ---------------------------------------------------------------------------

def leer_bundle_okf(item_id: str, source: str | None = None) -> str:
    """
    Lee el bundle OKF completo (Markdown + YAML frontmatter) de un ítem.
    Si 'source' no se pasa, lo infiere del prefijo del id.
    """
    if not source:
        for src in ("funcas", "bbva", "ine"):
            if item_id.startswith(src):
                source = src
                break

    if not source or source not in OKF_DIRS:
        return json.dumps({
            "error": f"No se pudo determinar la fuente para id='{item_id}'. "
                     "Pasa source='funcas'|'bbva'|'ine' explícitamente."
        })

    okf_dir = OKF_DIRS[source]
    slug = re.sub(rf"^{source}-", "", item_id)
    candidatos = [
        okf_dir / f"{item_id}.md",
        okf_dir / f"{slug}.md",
    ]

    for ruta in candidatos:
        if ruta.exists():
            contenido = ruta.read_text(encoding="utf-8")
            return json.dumps({
                "id":      item_id,
                "source":  source,
                "path":    str(ruta),
                "content": contenido,
            }, ensure_ascii=False)

    # Búsqueda flexible
    if okf_dir.exists():
        for f in okf_dir.glob("*.md"):
            if slug in f.stem or f.stem in slug:
                contenido = f.read_text(encoding="utf-8")
                return json.dumps({
                    "id":      item_id,
                    "source":  source,
                    "path":    str(f),
                    "content": contenido,
                    "nota":    "Encontrado por coincidencia parcial de slug",
                }, ensure_ascii=False)

    return json.dumps({
        "error": f"Bundle OKF no encontrado para id='{item_id}' en {okf_dir}",
        "candidatos_probados": [str(c) for c in candidatos],
    })


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Elimina acentos y diacríticos de un string."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# HERRAMIENTA 4 — obtener_datos_ine
# ---------------------------------------------------------------------------

def obtener_datos_ine(
    table_id: int,
    operation_code: str = None,
    fecha_desde: str = None,
    fecha_hasta: str = None,
    max_series: int = 5,
    max_valores: int = 20,
) -> str:
    """
    Llama a la API REST del INE en tiempo real y devuelve datos numéricos
    de una tabla concreta.

    Args:
        table_id: ID numérico de la tabla INE (ej. 24077 para IPC general)
        operation_code: Código de la operación (ej. "IPC") — solo informativo
        fecha_desde: Fecha inicial (YYYY-MM-DD o YYYYMMDD)
        fecha_hasta: Fecha final (YYYY-MM-DD o YYYYMMDD)
        max_series: Máximo de series a devolver (default 5)
        max_valores: Máximo de valores por serie (default 20, 0=todos)

    Returns:
        JSON con series, valores, metadatos de la tabla
    """
    import urllib.request

    # Construir URL
    base = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA"
    url = f"{base}/{table_id}"
    params = []
    if fecha_desde and fecha_hasta:
        # Normalizar formato: quitar guiones si los tiene
        d1 = fecha_desde.replace("-", "")
        d2 = fecha_hasta.replace("-", "")
        params.append(f"date={d1}:{d2}")
    elif fecha_desde:
        d1 = fecha_desde.replace("-", "")
        params.append(f"date={d1}:")
    if params:
        url += "?" + "&".join(params)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return json.dumps({
            "error": f"HTTP {e.code} al consultar tabla {table_id}",
            "url": url,
        })
    except Exception as e:
        return json.dumps({
            "error": f"Error al consultar INE: {str(e)}",
            "url": url,
        })

    if not isinstance(data, list):
        return json.dumps({"error": "Respuesta inesperada de la API", "url": url})

    # Formatear respuesta
    series = []
    for s in data[:max_series]:
        cod = s.get("COD", "")
        nombre = s.get("Nombre", "")
        valores_raw = s.get("Data", [])

        # Limitar valores
        if max_valores > 0:
            valores_raw = valores_raw[-max_valores:]

        valores = []
        for v in valores_raw:
            try:
                ts = v["Fecha"] / 1000
                fecha = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (KeyError, TypeError):
                fecha = str(v.get("Fecha", ""))

            valores.append({
                "fecha": fecha,
                "periodo": v.get("FK_Periodo"),
                "anyo": v.get("Anyo"),
                "valor": v.get("Valor"),
            })

        series.append({
            "codigo": cod,
            "nombre": nombre,
            "valores_count": len(valores_raw),
            "valores": valores,
        })

    return json.dumps({
        "tabla_id": table_id,
        "operation_code": operation_code,
        "url_api": url,
        "series_count": len(data),
        "mostrando": len(series),
        "series": series,
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# HERRAMIENTA 5 — buscar_semantico
# ---------------------------------------------------------------------------

def _cargar_indice_semantico():
    """Carga embeddings, IDs y títulos en memoria (lazy, una vez)."""
    global _SEM_EMBEDDINGS, _SEM_IDS, _SEM_TITLES
    if _SEM_EMBEDDINGS is not None:
        return
    try:
        import numpy as np
        emb_path = BASE_DIR / "processed" / "embeddings.npy"
        ids_path = BASE_DIR / "processed" / "embedding_ids.json"
        titles_path = BASE_DIR / "processed" / "embedding_titles.json"

        _SEM_EMBEDDINGS = np.load(str(emb_path))
        with open(ids_path, encoding="utf-8") as f:
            _SEM_IDS = json.load(f)
        with open(titles_path, encoding="utf-8") as f:
            _SEM_TITLES = json.load(f)
        print(f"Índice semántico cargado: {_SEM_EMBEDDINGS.shape}")
    except Exception as e:
        print(f"Error cargando índice semántico: {e}")
        raise

_SEM_EMBEDDINGS = None
_SEM_IDS = None
_SEM_TITLES = None


def buscar_semantico(
    texto: str,
    max_resultados: int = 10,
    min_score: float = 0.0,
) -> str:
    """
    Busca en el catálogo por similitud semántica (significado).
    No busca palabras exactas — entiende el concepto.
    """
    _cargar_indice_semantico()

    # Embedizar la consulta
    import urllib.request
    payload = json.dumps({
        "model": "nomic-embed-text-v2-moe",
        "prompt": texto,
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    q_emb = json.loads(resp.read().decode())["embedding"]

    # Cosine similarity
    import numpy as np
    q_vec = np.array(q_emb, dtype=np.float32)
    norms = np.linalg.norm(_SEM_EMBEDDINGS, axis=1)
    q_norm = np.linalg.norm(q_vec)
    if q_norm == 0:
        return json.dumps({"error": "No se pudo generar embedding para la consulta"})

    sims = np.dot(_SEM_EMBEDDINGS, q_vec) / (norms * q_norm + 1e-10)
    indices = np.argsort(sims)[::-1]

    resultados = []
    cat = _catalogo()
    for idx in indices:
        score = float(sims[idx])
        if score < min_score:
            break
        item_id = _SEM_IDS[idx]
        # Buscar en catálogo
        item = next((r for r in cat if r.get("id") == item_id), None)
        if not item:
            continue
        resultados.append({
            "id": item_id,
            "title": item.get("title", _SEM_TITLES[idx]),
            "source": item.get("source"),
            "date_iso": item.get("date_iso"),
            "description": (item.get("description") or "")[:150],
            "url": item.get("url"),
            "score": round(score, 4),
        })
        if len(resultados) >= max_resultados:
            break

    return json.dumps({
        "consulta": texto,
        "total_encontrados": len(resultados),
        "resultados": resultados,
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# DEFINICIÓN DE HERRAMIENTAS PARA EL LLM
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "listar_fuentes",
            "description": (
                "Devuelve un resumen del catálogo OKF de economía española: "
                "total de ítems, desglose por fuente (Funcas/BBVA/INE), tipos "
                "disponibles, rango temporal y tags más frecuentes. "
                "Úsalo siempre como primer paso para orientarte antes de buscar."
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_catalogo",
            "description": (
                "Filtra los ítems del catálogo OKF usando criterios combinables. "
                "Úsalo para encontrar documentos, datasets u operaciones estadísticas "
                "relevantes para la pregunta del usuario. Todos los parámetros son opcionales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["funcas", "bbva", "ine"],
                        "description": "Fuente: 'funcas' (documentos), 'bbva' (publicaciones), 'ine' (operaciones estadísticas)",
                    },
                    "tipo": {
                        "type": "string",
                        "description": "Tipo real: 'working_paper' (Funcas), 'report' (BBVA/Funcas), 'dataset' (INE)",
                    },
                    "desde": {"type": "string", "description": "Fecha ISO mínima, ej. '2020-01-01'"},
                    "hasta": {"type": "string", "description": "Fecha ISO máxima, ej. '2024-12-31'"},
                    "texto": {"type": "string", "description": "Texto en título/descripción (insensible a acentos)"},
                    "tags": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Tags que deben estar TODOS presentes",
                    },
                    "geography": {
                        "type": "string",
                        "description": "Solo BBVA: 'España', 'Global', 'México', etc.",
                    },
                    "max_resultados": {
                        "type": "integer",
                        "description": "Límite de resultados (default 20, recomendado max 50)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leer_bundle_okf",
            "description": (
                "Lee el bundle OKF completo (Markdown + metadatos YAML) de un ítem "
                "concreto. Úsalo cuando necesites el detalle completo. "
                "Requiere el 'id' obtenido con buscar_en_catalogo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "ID del ítem, ej. 'funcas-politica-monetaria', 'ine-ipc'",
                    },
                    "source": {
                        "type": "string", "enum": ["funcas", "bbva", "ine"],
                        "description": "Fuente (opcional si el id incluye prefijo)",
                    },
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_datos_ine",
            "description": (
                "Llama a la API REST del INE en tiempo real y devuelve datos numéricos "
                "de una tabla concreta. Úsalo cuando el usuario pregunte por valores "
                "concretos: IPC, inflación, paro, PIB, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_id": {
                        "type": "integer",
                        "description": "ID numérico de la tabla INE (ej. 24077 para IPC general)",
                    },
                    "operation_code": {
                        "type": "string",
                        "description": "Código de la operación (ej. 'IPC', 'EPA', 'IPCA')",
                    },
                    "fecha_desde": {
                        "type": "string",
                        "description": "Fecha inicial (YYYY-MM-DD), ej. '2024-01-01'",
                    },
                    "fecha_hasta": {
                        "type": "string",
                        "description": "Fecha final (YYYY-MM-DD), ej. '2026-07-27'",
                    },
                    "max_series": {
                        "type": "integer",
                        "description": "Máximo de series a devolver (default 5)",
                    },
                    "max_valores": {
                        "type": "integer",
                        "description": "Máximo de valores por serie (default 20, 0=todos)",
                    },
                },
                "required": ["table_id"],
            },
        },
    },
]

# Mapa de funciones ejecutables
FUNC_MAP = {
    "listar_fuentes":      lambda args: listar_fuentes(),
    "buscar_en_catalogo":  lambda args: buscar_en_catalogo(**args),
    "leer_bundle_okf":     lambda args: leer_bundle_okf(**args),
    "obtener_datos_ine":   lambda args: obtener_datos_ine(**args),
    "buscar_semantico":    lambda args: buscar_semantico(**args),
}


# ---------------------------------------------------------------------------
# TOOL 5 — buscar_semantico (añadir a TOOLS arriba)
# ---------------------------------------------------------------------------
# Nota: buscar_semantico se añade programáticamente a TOOLS
_SEM_TOOL = {
    "type": "function",
    "function": {
        "name": "buscar_semantico",
        "description": (
            "Busca en el catálogo por significado, no por palabras exactas. "
            "Úsalo para preguntas conceptuales donde las palabras concretas "
            "no aparecen en los títulos. Ej: 'impacto de la inflación en hogares' "
            "encontrará documentos sobre IPC, poder adquisitivo, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {
                    "type": "string",
                    "description": "Texto o frase a buscar semánticamente",
                },
                "max_resultados": {
                    "type": "integer",
                    "description": "Máximo de resultados (default 10)",
                },
                "min_score": {
                    "type": "number",
                    "description": "Score mínimo de similitud (0.0-1.0, default 0.0)",
                },
            },
            "required": ["texto"],
        },
    },
}
TOOLS.append(_SEM_TOOL)


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Eres un asistente especializado en economía española con acceso al \
repositorio OKF de datos económicos. El catálogo contiene 1.052 ítems de tres fuentes, \
y puedes consultar la API del INE en tiempo real para obtener datos numéricos:

- **Funcas**: 930 documentos de trabajo y notas técnicas (2011–2026)
- **BBVA Research**: 10 publicaciones con enfoque en big data y España
- **INE**: 112 operaciones estadísticas (IPC, EPA, PIB, vivienda, turismo, etc.) \
  con acceso a 3.4M de valores via API REST pública

Instrucciones de uso de herramientas:
1. Empieza siempre con listar_fuentes si no sabes qué hay disponible.
2. Usa buscar_en_catalogo para filtrar ítems relevantes. Combina parámetros.
3. **Para búsqueda por concepto** (no por palabra exacta), usa buscar_semantico. \
   Ej: 'impacto inflación hogares' encuentra IPC, poder adquisitivo, etc.
4. Usa leer_bundle_okf solo para los ítems más relevantes (cuesta tokens).
5. **Para datos numéricos concretos** (IPC, inflación, paro, PIB...), usa \
   obtener_datos_ine con el table_id. **IMPORTANTE: Siempre pasa fecha_desde \
   y fecha_hasta juntos** — sin fecha_desde la API del INE devuelve solo \
   datos históricos (pre-2002). Si el usuario no da fechas, usa los últimos \
   12 meses como defecto.
5. Basa tus respuestas ÚNICAMENTE en los datos leídos. Si algo no está en el \
   catálogo, dilo explícitamente.
6. Separa siempre DATOS DEL CATÁLOGO de ESTIMACIONES PROPIAS."""




# ---------------------------------------------------------------------------
# BUCLE DE EJECUCIÓN
# ---------------------------------------------------------------------------

def consultar(pregunta: str, verbose: bool = False) -> str:
    """
    Envía una pregunta al agente y devuelve la respuesta final.
    El agente puede encadenar múltiples llamadas a herramientas.
    verbose=True imprime el razonamiento intermedio.
    """
    client, modelo = _conectar()

    mensajes = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": pregunta},
    ]

    MAX_ITERACIONES = 8

    for iteracion in range(MAX_ITERACIONES):
        respuesta = client.chat.completions.create(
            model=modelo,
            messages=mensajes,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = respuesta.choices[0].message

        if not msg.tool_calls:
            return msg.content

        if verbose:
            for tc in msg.tool_calls:
                print(f"  → [{iteracion+1}] {tc.function.name}({tc.function.arguments})")

        mensajes.append(msg)

        for tc in msg.tool_calls:
            nombre = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            if nombre in FUNC_MAP:
                resultado = FUNC_MAP[nombre](args)
            else:
                resultado = json.dumps({"error": f"Herramienta desconocida: {nombre}"})

            mensajes.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "name":         nombre,
                "content":      resultado,
            })

    return "El agente alcanzó el límite de iteraciones sin producir una respuesta final."


# ---------------------------------------------------------------------------
# CLI INTERACTIVO
# ---------------------------------------------------------------------------

def main():
    # Forzar carga del catálogo antes de entrar al bucle
    try:
        cat = _catalogo()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    print("=" * 60)
    print(f"Agente OKF — Economía Española")
    print(f"Modo: {MODO}")
    print(f"Catálogo: {CATALOG_PATH} ({len(cat)} ítems)")
    print(f"Fuentes: Funcas={sum(1 for r in cat if r.get('source')=='Funcas')}, "
          f"BBVA={sum(1 for r in cat if 'BBVA' in r.get('source',''))}, "
          f"INE={sum(1 for r in cat if r.get('source')=='INE')}")
    print("Escribe 'salir' para terminar.")
    print("=" * 60)

    while True:
        try:
            pregunta = input("Pregunta: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if pregunta.lower() in ("salir", "exit", "quit"):
            print("Hasta luego.")
            break
        if not pregunta:
            continue

        print("\nPensando...\n")
        try:
            respuesta = consultar(pregunta, verbose=True)
            print(f"\nRespuesta:\n{respuesta}\n")
        except (ImportError, ValueError, ConnectionError) as e:
            print(f"❌ Error de configuración: {e}")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
        print("-" * 60)


if __name__ == "__main__":
    main()
