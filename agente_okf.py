#!/usr/bin/env python3
"""
Agente de consulta OKF — Repositorio Economía Española
Herramientas adaptadas al esquema real de catalog.jsonl y bundles okf/

Esquema de catalog.jsonl:
  id, source, title, date_iso, description, tags, url, type,
  normalized_at, authors (Funcas), geography/technique (BBVA),
  tables_count/series_count/values_count (INE)

Uso:
  pip install openai pyyaml python-dotenv
  export OPENROUTER_API_KEY=...   # o AGENTE_MODO=OLLAMA
  python agente_okf.py
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# BACKEND OPCIONAL: solo falla si se intenta usar sin tener instalado openai
# ---------------------------------------------------------------------------
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # Se comprueba al conectar

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

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
        modelo = os.getenv("AGENTE_MODELO", "nous-hermes-3-llama-3.1-70b")
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
            "tags", "url", "type", "authors",          # Funcas
            "geography", "technique",                   # BBVA
            "tables_count", "series_count", "values_count",  # INE
        ],
    }
    return json.dumps(resumen, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# HERRAMIENTA 2 — buscar_en_catalogo
# ---------------------------------------------------------------------------

def buscar_en_catalogo(
    source: str | None = None,
    tipo: str | None = None,
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

    for r in cat:
        if source and r.get("source", "").lower() != source.lower():
            continue
        if tipo and r.get("type", "").lower() != tipo.lower():
            continue
        if desde and (r.get("date_iso") or "") < desde:
            continue
        if hasta and (r.get("date_iso") or "") > hasta:
            continue
        if texto_lower:
            haystack = (
                (r.get("title") or "").lower()
                + " "
                + (r.get("description") or "").lower()
            )
            if texto_lower not in haystack:
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
                        "description": "Fuente: 'funcas', 'bbva' o 'ine'",
                    },
                    "tipo": {
                        "type": "string",
                        "description": "'documento_trabajo', 'dataset' o 'report'",
                    },
                    "desde": {"type": "string", "description": "Fecha ISO mínima, ej. '2020-01-01'"},
                    "hasta": {"type": "string", "description": "Fecha ISO máxima, ej. '2024-12-31'"},
                    "texto": {"type": "string", "description": "Texto en título/descripción"},
                    "tags": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Tags que deben estar TODOS presentes",
                    },
                    "geography": {
                        "type": "string",
                        "description": "Solo BBVA: 'España' o 'Global'",
                    },
                    "max_resultados": {
                        "type": "integer",
                        "description": "Límite de resultados (default 20)",
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
]

# Mapa de funciones ejecutables
FUNC_MAP = {
    "listar_fuentes":    lambda args: listar_fuentes(),
    "buscar_en_catalogo": lambda args: buscar_en_catalogo(**args),
    "leer_bundle_okf":   lambda args: leer_bundle_okf(**args),
}


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Eres un asistente especializado en economía española con acceso al \
repositorio OKF de datos económicos. El catálogo contiene 1.052 ítems de tres fuentes:

- **Funcas**: 930 documentos de trabajo y notas técnicas (2011–2026)
- **BBVA Research**: 10 publicaciones con enfoque en big data y España
- **INE**: 112 operaciones estadísticas (IPC, EPA, PIB, vivienda, turismo, etc.) \
  con acceso a 3.4M de valores via API REST pública

Instrucciones de uso de herramientas:
1. Empieza siempre con listar_fuentes si no sabes qué hay disponible.
2. Usa buscar_en_catalogo para filtrar ítems relevantes. Combina parámetros.
3. Usa leer_bundle_okf solo para los ítems más relevantes (cuesta tokens).
4. Basa tus respuestas ÚNICAMENTE en los datos leídos. Si algo no está en el \
   catálogo, dilo explícitamente.
5. Cuando cites datos del INE, indica el endpoint de API si está disponible.
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
    print("=" * 60)
    print("Agente OKF — Economía Española")
    print(f"Modo: {MODO}")
    print(f"Catálogo: {CATALOG_PATH}")
    print("Escribe 'salir' para terminar.")
    print("=" * 60)

    try:
        cat = _catalogo()
        print(f"✅ Catálogo cargado: {len(cat)} ítems\n")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

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
        except (ImportError, ValueError) as e:
            print(f"❌ {e}")
        print("-" * 60)


if __name__ == "__main__":
    main()
