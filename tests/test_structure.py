"""Tests estructurales offline — verifican que el proyecto es consistente.

Todos estos tests funcionan sin conexión externa y sin polars.
Se ejecutan en CI en cada push.
"""
import sys
import json
from pathlib import Path

# ===========================================================================
# Tests de importabilidad
# ===========================================================================

class TestImports:
    """Los módulos principales deben importarse sin errores."""

    def test_config_imports(self):
        """config.py debe importarse sin errores."""
        from src.python import config
        assert config.BASE_DIR is not None
        assert isinstance(config.BASE_DIR, Path)
        assert isinstance(config.INE_API_BASE, str)
        assert config.INE_API_BASE.startswith("https://")

    def test_log_utils_imports(self):
        """log_utils.py debe importarse y crear logger."""
        from src.python import log_utils
        log = log_utils.ScrapeLogger("test", "TEST")
        assert log.source == "TEST"
        assert log.log is not None

    def test_hooks_imports(self):
        """hooks/__init__.py debe importar las funciones de seguridad."""
        from src.python.hooks import (
            SecurityError, secure_fs_jail, hook_no_net_python,
            secure_hmac_hash, hash_file_atomically, SecurityASTNodeVisitor
        )
        assert SecurityError is not None
        assert secure_fs_jail is not None
        assert hook_no_net_python is not None


# ===========================================================================
# Tests de estructura del repositorio
# ===========================================================================

class TestRepoStructure:
    """El repositorio debe tener la estructura de directorios esperada."""

    REPO = Path(__file__).resolve().parent.parent

    def test_readme_exists(self):
        """README.md debe existir en la raíz."""
        assert (self.REPO / "README.md").exists(), "README.md no encontrado"

    def test_requirements_exists(self):
        """requirements.txt debe existir con contenido."""
        req = self.REPO / "requirements.txt"
        assert req.exists(), "requirements.txt no encontrado"
        content = req.read_text()
        assert len(content) > 50, "requirements.txt parece vacío"
        assert "pytest" in content, "requirements.txt debe listar pytest"

    def test_agente_exists(self):
        """agente_okf.py debe existir en la raíz."""
        assert (self.REPO / "agente_okf.py").exists(), "agente_okf.py no encontrado"

    def test_src_python_exists(self):
        """src/python/ debe tener los módulos core."""
        src = self.REPO / "src" / "python"
        assert (src / "config.py").exists()
        assert (src / "log_utils.py").exists()
        assert (src / "hooks" / "__init__.py").exists()

    def test_pipeline_scripts_exist(self):
        """Los pipelines deben existir."""
        pip = self.REPO / "src" / "python" / "pipelines"
        assert (pip / "normalize.py").exists(), "normalize.py no encontrado"
        assert (pip / "embeddings.py").exists(), "embeddings.py no encontrado"

    def test_ci_workflow_exists(self):
        """El workflow de CI debe existir."""
        ci = self.REPO / ".github" / "workflows" / "ci.yml"
        assert ci.exists(), ".github/workflows/ci.yml no encontrado"


# ===========================================================================
# Tests de catálogo (dataset verificado)
# ===========================================================================

class TestCatalog:
    """El catálogo procesado debe tener contenido válido."""

    REPO = Path(__file__).resolve().parent.parent
    CATALOG = REPO / "processed" / "catalog.jsonl"

    def test_catalog_exists(self):
        """catalog.jsonl debe existir."""
        assert self.CATALOG.exists(), "processed/catalog.jsonl no encontrado"

    def test_catalog_is_not_empty(self):
        """catalog.jsonl debe tener al menos 1 línea."""
        lines = [l for l in self.CATALOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) > 0, "catalog.jsonl está vacío"

    def test_catalog_has_expected_items(self):
        """catalog.jsonl debe tener ~4295 ítems (con ECB)."""
        lines = [l for l in self.CATALOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 4000, f"catalog.jsonl tiene {len(lines)} líneas, esperaba >=4000"
        assert len(lines) <= 4500, f"catalog.jsonl tiene {len(lines)} líneas, esperaba <=4500"

    def test_catalog_lines_are_valid_json(self):
        """Cada línea de catalog.jsonl debe ser JSON válido con campos mínimos."""
        lines = [l for l in self.CATALOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        for i, line in enumerate(lines[:50]):  # Muestrear primeras 50
            item = json.loads(line)
            assert "id" in item, f"Línea {i+1}: falta 'id'"
            assert "title" in item, f"Línea {i+1}: falta 'title'"
            assert "source" in item, f"Línea {i+1}: falta 'source'"
            assert item['source'] in ('Funcas', 'BBVA Research', 'INE', 'ECB', 'funcas', 'bbva', 'ine'), \
                f"Línea {i+1}: source '{item['source']}' inválido"

    def test_catalog_has_four_sources(self):
        """El catálogo debe contener datos de las 4 fuentes."""
        lines = [l for l in self.CATALOG.read_text(encoding="utf-8").splitlines() if l.strip()]
        sources = set()
        for line in lines:
            item = json.loads(line)
            sources.add(item.get("source", ""))
        assert 'Funcas' in sources, 'Faltan datos de Funcas'
        assert 'BBVA Research' in sources or 'bbva' in sources, 'Faltan datos de BBVA'
        assert 'INE' in sources, 'Faltan datos de INE'
        assert 'ECB' in sources, 'Faltan datos de ECB (Banco Central Europeo)'
