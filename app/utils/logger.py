"""
Logger wrapper para InmuebleBot.
Mantiene backwards compatibility con el ecosistema loguru existente.
"""
from loguru import logger

# Re-exportar logger para compatibilidad
__all__ = ["logger"]