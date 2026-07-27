"""Logging estructurado para el Repositorio OKF.

Reemplaza los print() y except: pass silenciosos por logs
con timestamp, nivel y contexto.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.python.config import LOGS_DIR

def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Configura un logger con salida a archivo y consola."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()  # Evitar duplicados

    # Formato: timestamp | nivel | mensaje
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler archivo (persistente)
    log_file = LOGS_DIR / f"{name}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Handler consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


class ScrapeLogger:
    """Wrapper que añade contexto de scraper (fuente, url)."""

    def __init__(self, name: str, source: str):
        self.log = setup_logger(name)
        self.source = source

    def info(self, msg: str, **ctx):
        extra = f" [{self.source}]"
        if ctx:
            extra += " | " + " ".join(f"{k}={v}" for k, v in ctx.items())
        self.log.info("%s%s", msg, extra)

    def warning(self, msg: str, **ctx):
        extra = f" [{self.source}]"
        if ctx:
            extra += " | " + " ".join(f"{k}={v}" for k, v in ctx.items())
        self.log.warning("%s%s", msg, extra)

    def error(self, msg: str, exc_info=False, **ctx):
        extra = f" [{self.source}]"
        if ctx:
            extra += " | " + " ".join(f"{k}={v}" for k, v in ctx.items())
        self.log.error("%s%s", msg, extra, exc_info=exc_info)
