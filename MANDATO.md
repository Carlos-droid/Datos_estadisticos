# Marco de Desarrollo: Sistema de Cruce de Datos Híbrido (R + Python + IA)

**Versión:** 3.0 (Enterprise Agentic Grade)

Este documento define la arquitectura, reglas, flujos de trabajo, observabilidad, y la implementación de código central para un proyecto de orquestación y cruce de datos masivos.

El sistema integra **R** (análisis estadístico) y **Python (Polars + DuckDB)** (ingeniería masiva), coordinados por un sistema multi-agente en **LangGraph**. El marco opera bajo el paradigma **Spec-First & Deterministic Verification** para evitar alucinaciones, fugas de PII y sobrecostes, asumiendo que el agente es un actor "no confiable" que debe ser validado por barreras duras (Hooks y Reviewers).

---

## 1. Arquitectura de Directorios y Entorno

### 1.1 Estructura de Directorios

```
data-crossing-framework/
├─ data/                          # Gestionado por DVC (.dvcignore ignora scratch)
├─ scratch/                       # Almacenamiento temporal concurrente ({run_id}/)
├─ src/
│  ├─ R/                          # Scripts R (estadística, pointblank)
│  ├─ python/
│  │  ├─ agents/                  # LangGraph (state.py, nodes.py, graph.py)
│  │  ├─ hooks/                   # Interceptores de seguridad (PII, Red, FS)
│  │  ├─ reviewers/               # Revisores adversariales deterministas
│  │  └─ pipelines/               # Lógica ETL pesada (Polars + DuckDB)
│  └─ bridge/                     # Orquestación R↔️Python (arrow/reticulate)
├─ schemas/                       # Contratos de datos
│  └─ canonical_types.yaml
├─ specs/                         # Paradigma Spec-First
│  ├─ open-spec/                  # RFCs y templates obligatorios de cruce
│  └─ learnings.md               # Reglas extraídas del proceso /retro
├─ workflows/                     # Definiciones YAML de flujos
├─ tests/                         # Unit, Contract, Property, e2e
├─ config/                        # dvc.yaml, conda-lock.yml, renv.lock
└─ Dockerfile                     # Basado en rocker/r-ver:4.4
```

### 1.2 Gobierno de Entorno y Memoria

- **Contenedor Base:** Docker con `rocker/r-ver:4.4`.
- **Entorno:** `micromamba` para binarios del sistema (Arrow/DuckDB) y Python bloqueado con `conda-lock.yml`. `renv` se aísla dentro del entorno conda (`RENV_PATHS_LIBRARY`).
- **Paso de Memoria R ↔️ Python:**
  - Cruces < 20MB: Paso en memoria (`r_to_py()` / `py_to_r()`).
  - Cruces > 20MB: Escritura obligatoria en disco (Apache Arrow, compresión zstd) en `scratch/{run_id}/bridge_{uuid}.parquet`.

---

## 2. Ciclo de Vida del Agente: Spec-First & Routing

Basado en el principio *"Coding was never the bottleneck"*, los agentes no tocan código o datos sin una especificación o sin calcular el tamaño de la tarea.

### 2.1 Auto-Sizer (Router Inicial)

| T-Shirt | Condiciones | Ruta |
|---|---|---|
| **S** (Tier 3 directo) | Cruce determinista (ON id=id), <100k filas, sin PII | No requiere Spec ni LLM pesado |
| **M** (Tier 2) | Drift de esquema detectado | Light Spec generada por agente + aprobación en terminal |
| **L** (Tier 1 + 2) | Cruce semántico complejo / N:M | Bloqueado hasta aprobación humana en `specs/open-spec/` |

### 2.2 Three-Tier Model Routing (Optimización de Costes)

| Tier | Modelo | Uso |
|---|---|---|
| **Tier 1** (SOTA) | GPT-4o / Claude 3.5 Sonnet | Planning, Specs, resolución de ambigüedades |
| **Tier 2** (Mid) | GPT-4o-mini / Claude 3.5 Haiku | Transformaciones, regex, Polars/DuckDB |
| **Tier 3** (Cheap/Local) | all-MiniLM-L6-v2 (embeddings), Llama-3 local / scripts QA | Match semántico, verificaciones deterministas |

---

## 3. Seguridad, Gobernanza y Bucle de Aprendizaje

### 3.1 Criptografía y Provenance

- **Hashing Seguro:** Todo ID o PII anonimizado usa **HMAC-SHA256**(secret_per_run + pepper_global, data).
- **Provenance Attestation:** LangGraph emite un JSON criptográfico inmutable por ejecución de nodo, conteniendo el **Hash TOCTOU** de inputs y outputs.

### 3.2 El Bucle Continuo (`/retro`)

Al final de cruces complejos con intervención humana, LangGraph lanza una **entrevista socrática**. El resultado se convierte en regla determinista propuesta vía PR a `schemas/canonical_types.yaml`, para que futuros cruces sean T-Shirt S.

---

## 4. Implementación Core (Python / LangGraph)

### 4.1 Hooks de Seguridad (`src/python/hooks/security_hooks.py`)

```python
import os, re, ast, hmac, hashlib
from pathlib import Path
from typing import Union

class SecurityError(Exception): pass

def secure_fs_jail(requested_path: Union[str, Path], run_id: str, base_dir: str = "scratch") -> Path:
    """Confina el I/O del agente estrictamente a scratch/{run_id}/."""
    if not re.match(r"^[a-zA-Z0-9-]+$", run_id):
        raise ValueError(f"🚨 Seguridad: run_id inválido: {run_id}")
    expected_base = Path(base_dir).resolve() / run_id
    expected_base.mkdir(parents=True, exist_ok=True)
    requested = Path(requested_path).resolve()
    if not requested.is_relative_to(expected_base):
        raise PermissionError(f"🚨 Seguridad (FS-Jail): Intento de escape a {requested}")
    return requested

class SecurityASTNodeVisitor(ast.NodeVisitor):
    """Bloquea importaciones y llamadas a red/sistema a nivel de sintaxis."""
    FORBIDDEN_MODULES = {"os", "subprocess", "socket", "requests", "urllib", "httpx", "sys", "ftplib"}
    FORBIDDEN_FUNCTIONS = {"system", "popen", "run", "call", "eval", "exec"}
    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split('.')[0] in self.FORBIDDEN_MODULES:
                raise SecurityError(f"🚨 Bloqueo: Módulo {alias.name}")
        self.generic_visit(node)
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_FUNCTIONS:
            raise SecurityError(f"🚨 Bloqueo: Función {node.func.id}")
        self.generic_visit(node)

def hook_no_net_python(generated_code: str):
    SecurityASTNodeVisitor().visit(ast.parse(generated_code))

def secure_hmac_hash(data: str, secret_per_run: str, pepper_global: str) -> str:
    hmac_key = f"{secret_per_run}_{pepper_global}".encode('utf-8')
    return hmac.new(hmac_key, str(data).encode('utf-8'), hashlib.sha256).hexdigest()

def hash_file_atomically(filepath: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
```

### 4.2 Revisor de Fanout (`src/python/reviewers/fanout_reviewer.py`)

```python
import polars as pl
from typing import List, Literal

def reviewer_fanout_leak(
    df_a: pl.DataFrame, df_b: pl.DataFrame, df_result: pl.DataFrame,
    join_keys: List[str], join_type: Literal["inner", "left", "outer"] = "inner",
    expected_cardinality: Literal["1:1", "1:N", "N:M"] = "1:1",
    max_fanout_tolerance: float = 1.05
):
    """Bloquea si hay productos cartesianos silentes o pérdida masiva."""
    if not join_keys:
        raise ValueError("🚨 QA (Fanout): Producto cartesiano bloqueado (sin ON explícito).")
    for key in join_keys:
        if key not in df_result.columns:
            raise ValueError(f"🚨 QA (Fanout): Clave '{key}' no encontrada.")
    len_a, len_b, len_res = df_a.height, df_b.height, df_result.height
    if expected_cardinality == "1:1":
        if df_result.select(join_keys).is_duplicated().any():
            raise AssertionError("🚨 QA: Claves duplicadas en cruce 1:1. N:M subyacente.")
        if join_type == "inner" and len_res > min(len_a, len_b):
            raise AssertionError(f"🚨 QA: Explosión Inner. {len_res} > {min(len_a, len_b)}.")
    elif expected_cardinality == "1:N":
        max_expected = int(max(len_a, len_b) * max_fanout_tolerance)
        if len_res > max_expected:
            raise AssertionError(f"🚨 QA: Explosión catastrófica. {len_res} > {max_expected}.")
    if len_res == 0 and (len_a > 0 and len_b > 0):
        raise AssertionError("🚨 QA (Leakage): Join devolvió 0 filas.")
    return True
```

### 4.3 Orquestación LangGraph (`src/python/agents/graph.py`)

```python
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from src.python.hooks.security_hooks import hook_no_net_python, secure_fs_jail, SecurityError, hash_file_atomically
from src.python.reviewers.fanout_reviewer import reviewer_fanout_leak

class DataCrossingState(TypedDict):
    run_id: str
    tier_size: str
    input_paths: List[str]
    join_keys: List[str]
    generated_code: str
    scratch_output_path: str
    qa_passed: bool
    errors: List[str]
    provenance_log: Dict[str, Any]

def engineer_node(state: DataCrossingState) -> DataCrossingState:
    code, run_id = state["generated_code"], state["run_id"]
    try:
        hook_no_net_python(code)
        safe_out = secure_fs_jail(f"scratch/{run_id}/output_cross.parquet", run_id)
        safe_globals = {"pl": pl, "input_paths": state["input_paths"], "output_path": str(safe_out)}
        exec(code, safe_globals)
        state["scratch_output_path"] = str(safe_out)
        state["provenance_log"] = {"hash_output": hash_file_atomically(safe_out)}
        state["errors"] = []
    except Exception as e:
        state["errors"].append(f"Error Engineer: {str(e)}")
        state["qa_passed"] = False
    return state

def qa_node(state: DataCrossingState) -> DataCrossingState:
    if state["errors"]: return state
    try:
        df_a = pl.read_parquet(state["input_paths"][0])
        df_b = pl.read_parquet(state["input_paths"][1])
        df_result = pl.read_parquet(state["scratch_output_path"])
        reviewer_fanout_leak(df_a, df_b, df_result, state["join_keys"], "inner",
                             "1:1" if state["tier_size"] == "S" else "1:N")
        state["qa_passed"] = True
    except AssertionError as ae:
        state["errors"].append(str(ae))
        state["qa_passed"] = False
    return state
```

---

## 5. Observabilidad y CI/CD

### 5.1 Observabilidad

- **Logs Estructurados:** JSON (`{"timestamp": "...", "run_id": "...", "node": "...", "error": "..."}`).
- **Tracing:** OpenTelemetry en LangGraph.
- **Métricas Clave (Grafana):** `latencia_por_nodo`, `token_cost_run`, `fanout_ratio_average`.

### 5.2 CI/CD

- **Fast CI (on Push):** Tests Unitarios, Validación de AST Hooks y schemas de Pandera en < 3 min.
- **Nightly E2E:** Subsets sanitizados. Flujo completo LangGraph, prueba Llama-3 Tier 3, valida consistencia DataFrames en FS-Jail.
