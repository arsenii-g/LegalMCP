"""Base de datos local (SQLite + FTS5). Un solo fichero, sin servidor."""

import os
import sqlite3
import sys
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS normas (
    alias TEXT PRIMARY KEY,
    boe_id TEXT NOT NULL,
    nombre TEXT NOT NULL,
    titulo TEXT,
    rango TEXT,
    numero_oficial TEXT,
    url_eli TEXT,
    url_html TEXT,
    estado_consolidacion TEXT,
    fecha_actualizacion TEXT,
    descargado_en TEXT
);
CREATE TABLE IF NOT EXISTS bloques (
    id INTEGER PRIMARY KEY,
    alias TEXT NOT NULL,
    bloque_id TEXT NOT NULL,
    tipo TEXT,
    titulo TEXT,
    titulo_clave TEXT,
    ruta TEXT,
    orden INTEGER
);
CREATE INDEX IF NOT EXISTS ix_bloques_clave ON bloques(alias, titulo_clave);
CREATE TABLE IF NOT EXISTS versiones (
    id INTEGER PRIMARY KEY,
    bloque_pk INTEGER NOT NULL REFERENCES bloques(id),
    id_norma TEXT,
    fecha_publicacion TEXT,
    fecha_vigencia TEXT,
    fecha_hasta TEXT,
    texto TEXT,
    notas TEXT
);
CREATE INDEX IF NOT EXISTS ix_versiones_bloque ON versiones(bloque_pk);
CREATE VIRTUAL TABLE IF NOT EXISTS versiones_fts USING fts5(
    titulo, ruta, texto, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS cache (
    clave TEXT PRIMARY KEY,
    fuente TEXT,
    contenido TEXT,
    obtenido_en TEXT DEFAULT (datetime('now'))
);
"""


def directorio_datos() -> Path:
    if os.environ.get("NORMATIVA_MCP_DATA"):
        d = Path(os.environ["NORMATIVA_MCP_DATA"])
    elif sys.platform == "win32":
        d = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NormativaTributariaMCP"
    else:
        d = Path.home() / ".local" / "share" / "normativa-tributaria-mcp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(directorio_datos() / "normativa.sqlite", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(ESQUEMA)
    return con
