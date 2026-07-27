"""Revisores deterministas — auditoría post-ejecución.

Basado en MANDATO.md sección 4.2.
"""
import polars as pl
from typing import List, Literal


class FanoutError(AssertionError):
    """Error de fanout o leakage en cruce de datos."""
    pass


def reviewer_fanout_leak(
    df_a: pl.DataFrame,
    df_b: pl.DataFrame,
    df_result: pl.DataFrame,
    join_keys: List[str],
    join_type: Literal["inner", "left", "outer"] = "inner",
    expected_cardinality: Literal["1:1", "1:N", "N:M"] = "1:1",
    max_fanout_tolerance: float = 1.05,
) -> bool:
    """Bloquea la ejecución si hay productos cartesianos o pérdida masiva.

    Args:
        df_a: DataFrame izquierdo (input).
        df_b: DataFrame derecho (input).
        df_result: DataFrame resultante del cruce.
        join_keys: Columnas usadas como clave de cruce.
        join_type: Tipo de join esperado.
        expected_cardinality: Cardinalidad esperada.
        max_fanout_tolerance: Tolerancia máxima de crecimiento (1.05 = 5%).

    Returns:
        True si pasa todas las validaciones.

    Raises:
        ValueError: Si faltan claves o es producto cartesiano.
        FanoutError: Si hay duplicados inesperados, explosión o leakage.
    """
    # Validación 1: claves explícitas
    if not join_keys:
        raise ValueError(
            "🚨 QA (Fanout): Producto cartesiano bloqueado — "
            "no hay claves ON explícitas."
        )
    for key in join_keys:
        if key not in df_result.columns:
            raise ValueError(
                f"🚨 QA (Fanout): Clave '{key}' no encontrada "
                f"en el resultado. Columnas: {df_result.columns}"
            )

    len_a = df_a.height
    len_b = df_b.height
    len_res = df_result.height

    # Validación 2: cardinalidad 1:1
    if expected_cardinality == "1:1":
        if df_result.select(join_keys).is_duplicated().any():
            raise FanoutError(
                "🚨 QA: Claves duplicadas en cruce 1:1. "
                "Se detectó cardinalidad N:M subyacente."
            )
        if join_type == "inner" and len_res > min(len_a, len_b):
            raise FanoutError(
                f"🚨 QA: Explosión Inner Join. "
                f"{len_res} filas > {min(len_a, len_b)} esperadas."
            )
        if join_type == "left" and len_res != len_a:
            raise FanoutError(
                f"🚨 QA: Filtración Left Join. "
                f"{len_res} filas ≠ {len_a} esperadas."
            )

    # Validación 3: cardinalidad 1:N
    elif expected_cardinality == "1:N":
        max_expected = int(max(len_a, len_b) * max_fanout_tolerance)
        if len_res > max_expected:
            raise FanoutError(
                f"🚨 QA: Explosión catastrófica 1:N. "
                f"{len_res} filas > límite {max_expected} "
                f"(tolerancia {max_fanout_tolerance:.0%})."
            )

    # Validación 4: leakage (join vacío con datos origen)
    if len_res == 0 and (len_a > 0 and len_b > 0):
        raise FanoutError(
            "🚨 QA (Leakage): Join devolvió 0 filas. "
            "Falla total de mapeo entre datasets."
        )

    return True
