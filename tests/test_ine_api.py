"""Tests para el scraper del INE.

Verifica que:
1. La API responde correctamente
2. El parseo de operaciones funciona
3. El parseo de tablas funciona
4. El manejo de errores HTTP es correcto
5. El logging escribe a disco
"""
import json
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Añadir src/python al path (ruta absoluta)
SRC_PYTHON = str(Path(__file__).resolve().parent.parent / "src" / "python")
if SRC_PYTHON not in sys.path:
    sys.path.insert(0, SRC_PYTHON)

# ===========================================================================
# Tests de integración con la API real del INE
# ===========================================================================

class TestINEAPI:
    """Tests contra la API real del INE (requiere conexión)."""

    def test_api_returns_operations(self):
        """La API debe devolver lista de operaciones."""
        from config import INE_API_BASE, HTTP_HEADERS
        import urllib.request

        url = f"{INE_API_BASE}/OPERACIONES_DISPONIBLES"
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))

        assert isinstance(data, list), "Debe ser una lista"
        assert len(data) >= 100, f"Esperaba >=100 ops, tengo {len(data)}"
        assert any(op.get("Codigo") == "IPC" for op in data), "IPC debe existir"

    def test_ipc_has_tables(self):
        """El IPC debe tener tablas disponibles."""
        from config import INE_API_BASE, HTTP_HEADERS
        import urllib.request

        # Buscar IPC
        url = f"{INE_API_BASE}/OPERACIONES_DISPONIBLES"
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        ops = json.loads(resp.read().decode("utf-8"))
        ipc = [o for o in ops if o.get("Codigo") == "IPC"][0]

        # Pedir tablas del IPC
        url2 = f"{INE_API_BASE}/TABLAS_OPERACION/{ipc['Id']}"
        req2 = urllib.request.Request(url2, headers=HTTP_HEADERS)
        resp2 = urllib.request.urlopen(req2, timeout=15)
        tables = json.loads(resp2.read().decode("utf-8"))

        assert isinstance(tables, list), "Debe ser lista de tablas"
        assert len(tables) >= 10, f"IPC debe tener >=10 tablas, tengo {len(tables)}"
        assert any(t.get("Id") == 24077 for t in tables), "Tabla 24077 (IPC general) debe existir"

    def test_table_24077_has_ipc_data(self):
        """La tabla IPC general debe tener datos numéricos."""
        from config import INE_API_BASE, HTTP_HEADERS
        import urllib.request

        url = f"{INE_API_BASE}/DATOS_TABLA/24077"
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))

        assert isinstance(data, list), "Debe ser lista de series"
        assert len(data) >= 1, "Al menos 1 serie"
        serie = data[0]
        assert "COD" in serie, "Serie debe tener COD"
        assert "Data" in serie, "Serie debe tener Data (valores)"
        assert len(serie["Data"]) > 0, "Al menos 1 valor"
        primer_valor = serie["Data"][0]
        assert "Valor" in primer_valor, "Cada valor debe tener campo Valor"
        assert isinstance(primer_valor["Valor"], (int, float)), "Valor debe ser numérico"


# ===========================================================================
# Tests de hooks de seguridad
# ===========================================================================

class TestSecurityHooks:
    """Los hooks deben bloquear código peligroso."""

    def test_clean_code_passes(self):
        from hooks import hook_no_net_python, SecurityError
        code = """import polars as pl\ndf = pl.DataFrame({"x": [1,2,3]})\nprint(df)"""
        hook_no_net_python(code)  # No debe lanzar excepción

    def test_subprocess_blocked(self):
        from hooks import hook_no_net_python, SecurityError
        code = "import subprocess\nsubprocess.run(['ls'])"
        import pytest
        with pytest.raises(SecurityError, match="subprocess"):
            hook_no_net_python(code)

    def test_os_system_blocked(self):
        from hooks import hook_no_net_python, SecurityError
        code = "import os\nos.system('ls')"
        import pytest
        with pytest.raises(SecurityError, match="os"):
            hook_no_net_python(code)

    def test_eval_blocked(self):
        from hooks import hook_no_net_python, SecurityError
        code = "eval('1+1')"
        import pytest
        with pytest.raises(SecurityError, match="eval"):
            hook_no_net_python(code)

    def test_fs_jail_blocks_escape(self):
        from hooks import secure_fs_jail
        import pytest
        with pytest.raises(PermissionError):
            secure_fs_jail("/etc/passwd", "run-test-001")


# ===========================================================================
# Tests de reviewer de fanout
# ===========================================================================

class TestFanoutReviewer:
    """El reviewer debe detectar productos cartesianos y leakage."""

    def test_1_1_join_passes(self):
        """Cruce 1:1 correcto debe pasar."""
        pytest.importorskip("polars")
        import polars as pl
        from reviewers import reviewer_fanout_leak

        df_a = pl.DataFrame({"id": [1, 2, 3], "x": ["a", "b", "c"]})
        df_b = pl.DataFrame({"id": [1, 2, 3], "y": [10, 20, 30]})
        df_res = df_a.join(df_b, on="id")

        assert reviewer_fanout_leak(df_a, df_b, df_res, ["id"], "inner", "1:1") is True

    def test_empty_join_detected(self):
        """Join que devuelve 0 filas con datos origen debe fallar."""
        pytest.importorskip("polars")
        import polars as pl
        from reviewers import reviewer_fanout_leak, FanoutError

        df_a = pl.DataFrame({"id": [1, 2, 3], "x": ["a", "b", "c"]})
        df_b = pl.DataFrame({"id": [4, 5, 6], "y": [10, 20, 30]})
        df_res = df_a.join(df_b, on="id", how="inner")

        with pytest.raises(FanoutError, match="0 filas"):
            reviewer_fanout_leak(df_a, df_b, df_res, ["id"], "inner", "1:1")

    def test_cartesian_product_blocked(self):
        """Cruce sin claves debe ser bloqueado."""
        pytest.importorskip("polars")
        import polars as pl
        from reviewers import reviewer_fanout_leak

        df_a = pl.DataFrame({"x": [1, 2]})
        df_b = pl.DataFrame({"y": [3, 4]})
        # Producto cartesiano explícito
        df_res = pl.DataFrame({"x": [1, 1, 2, 2], "y": [3, 4, 3, 4]})

        with pytest.raises(ValueError, match="cartesiano"):
            reviewer_fanout_leak(df_a, df_b, df_res, [], "inner", "1:1")
