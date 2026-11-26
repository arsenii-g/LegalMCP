"""Descarga / actualiza la normativa del BOE en la base local.

    python -m normativa_mcp.ingest              # todas las normas del catálogo (solo las que cambiaron)
    python -m normativa_mcp.ingest LGT LIVA     # solo esas
    python -m normativa_mcp.ingest --forzar     # vuelve a descargar aunque no hayan cambiado
    python -m normativa_mcp.ingest --buscar "1065/2007"   # busca el identificador BOE de una norma
"""

import argparse
import json

import requests

from . import boe
from .catalogo import NORMAS
from .db import conectar, directorio_datos


def buscar_id(texto: str) -> None:
    q = {"query": {"query_string": {"query": f"numero_oficial:{texto}" if "/" in texto else f"titulo:{texto}"}}}
    r = requests.get(boe.API, params={"query": json.dumps(q), "limit": 10},
                     headers={**boe.UA, "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    for x in r.json().get("data", []):
        print(x["identificador"], "-", x["titulo"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("normas", nargs="*", help=f"alias a descargar ({', '.join(NORMAS)})")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--buscar")
    a = ap.parse_args()
    if a.buscar:
        return buscar_id(a.buscar)
    desconocidas = [n for n in a.normas if n.upper() not in NORMAS]
    if desconocidas:
        ap.error(f"alias desconocidos: {desconocidas}")
    con = conectar()
    print(f"Base de datos: {directorio_datos() / 'normativa.sqlite'}")
    for linea in boe.descargar_todo(con, [n.upper() for n in a.normas] or None, a.forzar):
        print(linea, flush=True)
    con.execute("INSERT INTO versiones_fts(versiones_fts) VALUES ('optimize')")
    con.commit()


if __name__ == "__main__":
    main()
