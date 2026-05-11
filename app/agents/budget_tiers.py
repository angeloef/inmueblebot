"""
Módulo de cálculo dinámico de tiers de presupuesto.

Calcula los percentiles P33 y P66 de los precios de propiedades
disponibles en la base de datos, con caché en memoria de 5 minutos.
"""

from __future__ import annotations

import math
import time
from typing import Optional

from loguru import logger
from sqlalchemy import select

from app.db.models import Property
from app.db.session import async_session_factory

# ---------------------------------------------------------------------------
# Cache en memoria
# ---------------------------------------------------------------------------

_cache: Optional[dict] = None
_cache_ts: float = 0.0
CACHE_TTL: float = 300.0  # 5 minutos


def _invalidate_cache() -> None:
    """Resetea la caché (útil en tests o recarga manual)."""
    global _cache, _cache_ts  # noqa: PLW0603
    _cache = None
    _cache_ts = 0.0


# ---------------------------------------------------------------------------
# Cálculo de percentiles con interpolación lineal
# ---------------------------------------------------------------------------


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """
    Calcula un percentil usando interpolación lineal (método tipo R-7,
    consistente con numpy.percentile por defecto).

    Parameters
    ----------
    sorted_values:
        Lista de valores **ordenada ascendentemente**.
    percentile:
        Percentil deseado en rango [0, 100].

    Returns
    -------
    Valor interpolado en el percentil solicitado.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_values[0]

    # Índice real según R-7 (lineal interpolation)
    idx = (percentile / 100.0) * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))

    if lo == hi:
        return sorted_values[lo]

    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


# ---------------------------------------------------------------------------
# Consulta a DB y construcción del dict de tiers
# ---------------------------------------------------------------------------


async def _fetch_prices() -> list[float]:
    """
    Obtiene la lista de precios de propiedades activas desde la DB.
    """
    async with async_session_factory() as session:
        stmt = select(Property.price).where(Property.status == "available")
        result = await session.execute(stmt)
        prices = [row[0] for row in result.all() if row[0] is not None]
    return prices


def _build_tiers_from_prices(prices: list[float]) -> dict:
    """
    Construye el dict de tiers a partir de una lista de precios.

    Calcula P33 (low_max) y P66 (med_max) usando interpolación lineal.
    Cuando hay menos de 3 propiedades se retornan valores por defecto.
    """
    n = len(prices)
    logger.debug("Calculando tiers de presupuesto desde {} propiedades", n)

    if n < 3:
        logger.info(
            "Menos de 3 propiedades activas ({}). Usando defaults.",
            n,
        )
        return {
            "low_max": 100_000,
            "med_max": 250_000,
            "min_price": 0,
            "max_price": 0,
            "total_properties": n,
        }

    sorted_prices = sorted(prices)
    p33 = _percentile(sorted_prices, 33.33)
    p66 = _percentile(sorted_prices, 66.67)

    # Redondear a enteros para mantener consistencia
    low_max = int(round(p33))
    med_max = int(round(p66))

    return {
        "low_max": low_max,
        "med_max": med_max,
        "min_price": int(round(sorted_prices[0])),
        "max_price": int(round(sorted_prices[-1])),
        "total_properties": n,
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


async def get_budget_tiers() -> dict:
    """
    Calcula P33 y P66 de todos los precios de propiedades disponibles.
    Los tiers se calculan dinámicamente desde la DB.
    Cachea en memoria por 5 minutos.

    Returns
    -------
    dict con las claves:
        - low_max:           int  → percentil 33 (tope del tier bajo)
        - med_max:           int  → percentil 66 (tope del tier medio)
        - min_price:         int  → precio mínimo encontrado
        - max_price:         int  → precio máximo encontrado
        - total_properties:  int  → cantidad de propiedades consideradas
    """
    global _cache, _cache_ts  # noqa: PLW0603

    now = time.monotonic()

    # Servir desde caché si aún es válida
    if _cache is not None and (now - _cache_ts) < CACHE_TTL:
        logger.debug("Sirviendo budget_tiers desde caché en memoria")
        return dict(_cache)  # copia superficial para evitar mutaciones externas

    # Recargar desde DB
    logger.info("Recalculando budget_tiers desde la base de datos")
    try:
        prices = await _fetch_prices()
    except Exception:
        logger.exception("Error al consultar precios en DB para budget_tiers")
        # Si hay error de DB pero tenemos caché expirada, servirla igual
        if _cache is not None:
            logger.warning("Sirviendo caché expirada como fallback tras error de DB")
            return dict(_cache)
        # Sin caché ni DB → defaults absolutos
        return {
            "low_max": 100_000,
            "med_max": 250_000,
            "min_price": 0,
            "max_price": 0,
            "total_properties": 0,
        }

    tiers = _build_tiers_from_prices(prices)

    # Actualizar caché
    _cache = tiers
    _cache_ts = now

    return dict(tiers)
