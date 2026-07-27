# Pipeline de Incorporación de Datos — Repositorio OKF Economía Española
====================================================================

Cada fuente tiene su propio mecanismo de actualización. La decisión
determinista vs. LLM depende de la naturaleza de los datos.

## 1. FUNCAS — Documentos de investigación

### Estrategia: DETERMINISTA + LLM ligero para metadatos

**Determinista (cron diario):**
1. Fetch sitemap: `wp-sitemap-posts-documentos_trabajo-1.xml`
2. Comparar `lastmod` con el último scrape guardado en `.hermes/skills/okf_economia/checkpoints/funcas_last.txt`
3. Si hay URLs nuevas o modificadas → descargar metadatos + PDF

**LLM local (clasificación):**
- Cada documento nuevo se pasa por un modelo local (gemma-2-2b o similar)
- Extraer: categoría económica, keywords, resumen estructurado
- Output structured JSON para el OKF bundle

```
cron: "0 6 * * *"  (diario a las 6am)
script: check_funcas_updates.py
  → determinista: sitemap diff
  → LLM: classify_new_docs.py (solo si hay novedades)
  → output: OKF bundles nuevos
```

## 2. BBVA RESEARCH — Publicaciones

### Estrategia: DETERMINISTA (scraping programado)

**Determinista (cron semanal):**
1. Scrapear páginas de publicaciones
2. Comparar títulos/URLs con el índice actual
3. Descargar solo las nuevas

**NO necesita LLM** — los títulos ya incluyen geografía y técnica
(España | Global, Con técnicas Big Data, etc.)

```
cron: "0 8 * * 1"  (lunes a las 8am)
script: check_bbva_updates.py
  → deterministic scrape + diff
  → descarga PDF si disponible
  → output: OKF bundles nuevos
```

## 3. INE — API JSON + HVD

### Estrategia: DETERMINISTA PURO

El INE ya tiene API estructurada con metadatos completos.

**Determinista (cron semanal):**
1. Fetch `OPERACIONES_DISPONIBLES` → detectar nuevas operaciones
2. Para cada operación existente, fetch `TABLAS_OPERACION/{id}` → nuevas tablas
3. Para cada tabla, fetch `DATOS_TABLA/{id}` con rango de fechas si aplica
4. HVD: check si hay nuevos datasets en la página HVD

**NO necesita LLM** — los datos ya vienen perfectamente estructurados
con nombres, códigos, unidades y valores numéricos.

```
cron: "0 10 * * 1"  (lunes a las 10am)
script: check_ine_updates.py
  → API diff operations + tables
  → descarga datos nuevos
  → descarga nuevos HVD
  → output: JSONL + OKF bundles
```

## 4. EXPERIMENTALES + FUTURO — Datos no estructurados

### Estrategia: LLM LOCAL

Para las estadísticas experimentales del INE y fuentes futuras
(Banco de España, etc.) que puedan venir en PDF o HTML no estructurado:

**LLM local (gemma-2-2b o similar):**
1. Scrapear página → raw text
2. LLM extrae: título, descripción, metodología, variables, periodicidad
3. LLM categoriza: tipo de dato, relevancia económica, etiquetas
4. Output estructurado → OKF bundle

```
script: process_experimental_with_llm.py
  → crawler obtiene raw text
  → LLM local structured extraction
  → validación + OKF output
```

## CHECKPOINT & REANUDACIÓN

Todas las fuentes guardan su progreso en:

```
/mnt/hdd/repositorio-okf-economia/.checkpoints/
├── funcas_last.txt          → última fecha de sitemap procesada
├── bbva_last.txt            → último título procesado
├── ine_operations.json      → IDs de operaciones ya procesadas
└── ine_hvd.txt              → IDs de HVD ya descargados
```

Esto permite reanudar si el proceso se interrumpe y ejecutar
solo la parte incremental en cada ciclo.
