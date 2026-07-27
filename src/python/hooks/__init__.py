"""Hooks de seguridad — interceptan al agente durante ejecución.

Basado en MANDATO.md sección 4.1. Confina el agente a:
- FS-Jail: solo puede leer/escribir en scratch/{run_id}/
- No-Net: bloquea imports y llamadas a red/sistema vía AST
- Hashing HMAC-SHA256 para anonimización PII
- TOCTOU hash para provenance attestation
"""
import ast
import hashlib
import hmac
import re
from pathlib import Path
from typing import Union


class SecurityError(Exception):
    """Error de seguridad recuperable (no fatal del sistema)."""
    pass


def secure_fs_jail(
    requested_path: Union[str, Path],
    run_id: str,
    base_dir: str = "scratch",
) -> Path:
    """Confina el I/O del agente estrictamente a scratch/{run_id}/.

    Args:
        requested_path: Ruta que el agente quiere usar.
        run_id: Identificador único de ejecución (solo alfanumérico + guiones).
        base_dir: Directorio raíz de scratch (por defecto "scratch").

    Returns:
        Path absoluto dentro de la jaula.

    Raises:
        ValueError: Si run_id tiene caracteres inválidos.
        PermissionError: Si la ruta solicitada escapa de la jaula.
    """
    if not re.match(r"^[a-zA-Z0-9-]+$", run_id):
        raise ValueError(
            f"🚨 Seguridad: run_id inválido: {run_id}. "
            "Solo caracteres alfanuméricos y guiones."
        )

    expected_base = Path(base_dir).resolve() / run_id
    expected_base.mkdir(parents=True, exist_ok=True)

    requested = Path(requested_path).resolve()
    if not str(requested).startswith(str(expected_base)):
        raise PermissionError(
            f"🚨 Seguridad (FS-Jail): Intento de escape a {requested}. "
            f"Límite: {expected_base}"
        )
    return requested


# ---------------------------------------------------------------------------
# AST Checker — bloquea código generado que intente acceder a red/sistema
# ---------------------------------------------------------------------------
FORBIDDEN_MODULES = {
    "os", "subprocess", "socket", "requests", "urllib",
    "httpx", "sys", "ftplib", "shutil", "signal", "ctypes",
}
FORBIDDEN_FUNCTIONS = {
    "system", "popen", "run", "call", "eval", "exec",
    "compile", "__import__", "open", "exit", "quit",
}


class SecurityASTNodeVisitor(ast.NodeVisitor):
    """Recorre el AST y bloquea imports/funciones peligrosas."""

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in FORBIDDEN_MODULES:
                raise SecurityError(
                    f"🚨 Bloqueo: Módulo prohibido '{alias.name}' "
                    f"en código generado."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            top = node.module.split(".")[0]
            if top in FORBIDDEN_MODULES:
                raise SecurityError(
                    f"🚨 Bloqueo: Import desde módulo prohibido "
                    f"'{node.module}'."
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_FUNCTIONS:
                raise SecurityError(
                    f"🚨 Bloqueo: Función prohibida '{node.func.id}' "
                    f"en código generado."
                )
        self.generic_visit(node)


def hook_no_net_python(generated_code: str):
    """Valida que código Python generado no use red ni sistema.

    Parsea el AST y lanza SecurityError si detecta infracciones.
    Útil como paso previo a exec() en el nodo Engineer de LangGraph.
    """
    try:
        tree = ast.parse(generated_code)
    except SyntaxError as e:
        raise SecurityError(
            f"🚨 Código generado tiene errores de sintaxis: {e}"
        )
    SecurityASTNodeVisitor().visit(tree)


# ---------------------------------------------------------------------------
# Hashing HMAC-SHA256 (Anti Length Extension Attack)
# ---------------------------------------------------------------------------
def secure_hmac_hash(
    data: str,
    secret_per_run: str,
    pepper_global: str,
) -> str:
    """Hash HMAC-SHA256 resistente a length extension.

    Args:
        data: Dato a hashear (ID, PII, etc.).
        secret_per_run: Secreto único por ejecución.
        pepper_global: Pepper global del sistema.

    Returns:
        Hash hexadecimal de 64 caracteres.
    """
    hmac_key = f"{secret_per_run}_{pepper_global}".encode("utf-8")
    return hmac.new(
        hmac_key, str(data).encode("utf-8"), hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# TOCTOU Hash (Time-of-Check to Time-of-Use)
# ---------------------------------------------------------------------------
def hash_file_atomically(filepath: Path) -> str:
    """SHA256 de un archivo, lectura atómica por bloques.

    Args:
        filepath: Ruta al archivo.

    Returns:
        Hash hexadecimal.
    """
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
