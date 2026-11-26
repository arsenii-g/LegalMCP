"""Servidor MCP «normativa-tributaria».

Arranque (stdio, lo lanza el cliente MCP: OpenCode, Hermes, LM Studio, Claude Desktop…):
    python -m normativa_mcp
"""

import re

from mcp.server.mcpserver import MCPServer

from . import boe, doctrina
from .catalogo import NORMAS, resolver_alias
from .db import conectar

INSTRUCCIONES = """Fuente de normativa tributaria española con citas verificables.
Reglas de uso:
1. No cite ningún artículo, consulta o resolución que no haya leído con estas herramientas en esta conversación.
2. Antes de citar un artículo, léalo con obtener_articulo. Si el caso es de un ejercicio pasado, pase la fecha
   del devengo o de los hechos para obtener la redacción vigente entonces.
3. Reproduzca la línea «CITA:» que devuelven las herramientas.
4. Si no encuentra fuente, dígalo («no encuentro fuente») en lugar de suponer.
5. Las búsquedas de DGT y TEAC salen a internet: no incluya nombres, NIF ni datos del cliente."""

mcp = MCPServer(name="normativa-tributaria", instructions=INSTRUCCIONES, version="0.1.0")
_con = conectar()


def _alias(ley: str | None) -> tuple[str | None, str | None]:
    if not ley:
        return None, None
    a = resolver_alias(ley)
    if not a:
        return None, f"No reconozco la norma «{ley}». Disponibles: {', '.join(NORMAS)}."
    return a, None


@mcp.tool()
def listar_normas() -> str:
    """Lista las normas descargadas en local (alias, nombre, fecha de actualización del BOE).
    Úsela para saber qué alias pasar en el parámetro `ley` de las demás herramientas."""
    return boe.listar_normas(_con)


@mcp.tool()
def buscar_normativa(consulta: str, ley: str | None = None, fecha: str | None = None,
                     max_resultados: int = 5) -> str:
    """Busca artículos en la normativa tributaria consolidada del BOE (búsqueda local, sin internet).

    Args:
        consulta: palabras clave en español, p. ej. «plazo duración actuaciones inspectoras» o
            «prorrata deducción subvenciones». Mejor términos jurídicos que frases largas.
        ley: opcional, alias de la norma (LGT, RGAT, LIVA, RIVA, LIRPF, LIS, RGRST, …) o su número («37/1992»).
        fecha: opcional, AAAA-MM-DD. Devuelve la redacción vigente en esa fecha (por defecto, hoy).
        max_resultados: número de artículos a devolver (1-20).
    """
    alias, err = _alias(ley)
    if err:
        return err
    return boe.buscar(_con, consulta, alias, fecha, max(1, min(int(max_resultados), 20)))


@mcp.tool()
def obtener_articulo(ley: str, articulo: str, fecha: str | None = None, apartado: str | None = None) -> str:
    """Devuelve el texto exacto de un artículo o disposición, con su cita y su historial de redacciones.

    Args:
        ley: alias (LGT, RGAT, LIVA…) o número oficial («58/2003»).
        articulo: «150», «95 bis», «art. 29», «DA 1ª», «disposición transitoria segunda», o el
            «id» que devuelve buscar_normativa (útil en el PGC, cuyas normas no son artículos).
        fecha: opcional, AAAA-MM-DD. Redacción vigente en esa fecha (clave para ejercicios ya cerrados).
            Si se omite, la redacción actual.
        apartado: opcional, solo ese apartado («6», «Dos»). Úselo en artículos largos para ahorrar contexto.
    """
    alias, err = _alias(ley)
    if err or not alias:
        return err or "Indique la norma."
    return boe.obtener_articulo(_con, alias, articulo, fecha, apartado)


@mcp.tool()
def buscar_consultas_dgt(consulta: str, tipo: str = "vinculantes", normativa: str | None = None,
                         desde: str | None = None, hasta: str | None = None, max_resultados: int = 10) -> str:
    """Busca consultas de la Dirección General de Tributos (buscador oficial PETETE, por internet).

    Args:
        consulta: términos de búsqueda (texto libre). SIN datos del cliente.
        tipo: «vinculantes» (por defecto), «generales» o «ambas».
        normativa: opcional, filtra por norma citada, p. ej. «Ley 37/1992» o «Ley 58/2003 art. 66».
        desde, hasta: opcional, fechas de salida AAAA-MM-DD.
        max_resultados: 1-20.
    """
    try:
        return doctrina.buscar_dgt(consulta, tipo, normativa, desde, hasta, max(1, min(int(max_resultados), 20)))
    except Exception as e:
        return f"No se pudo consultar la DGT ({type(e).__name__}: {e}). Inténtelo más tarde."


@mcp.tool()
def buscar_resoluciones_teac(consulta: str, solo_doctrina: bool = False, desde: str | None = None,
                             hasta: str | None = None, max_resultados: int = 10) -> str:
    """Busca criterios de los Tribunales Económico-Administrativos (TEAC y TEAR) en DYCTEA (por internet).

    Args:
        consulta: palabras que deben aparecer. SIN datos del cliente.
        solo_doctrina: True para limitarse a criterios vinculantes (doctrina del TEAC).
        desde, hasta: opcional, fechas de la resolución AAAA-MM-DD.
        max_resultados: 1-20.
    """
    try:
        return doctrina.buscar_teac(consulta, solo_doctrina, desde, hasta, max(1, min(int(max_resultados), 20)))
    except Exception as e:
        return f"No se pudo consultar DYCTEA ({type(e).__name__}: {e}). Inténtelo más tarde."


@mcp.tool()
def obtener_documento(id: str, texto_completo: bool = False, parte: int = 1) -> str:
    """Texto completo de una consulta de la DGT o de un criterio/resolución de los TEA.

    Args:
        id: número de consulta DGT («V1479-26», «0123-24») o id de DYCTEA tal como lo devuelve
            buscar_resoluciones_teac («TEAC:00/09428/2023/00/0/1»).
        texto_completo: solo TEA; True añade el texto íntegro de la resolución (largo).
        parte: los documentos largos se devuelven por partes de ~12.000 caracteres.
    """
    ident = id.strip()
    try:
        if ident.upper().startswith("TEAC:") or "/" in ident:
            return doctrina.obtener_teac(_con, re.sub(r"^TEAC:", "", ident, flags=re.I), texto_completo, parte)
        return doctrina.obtener_dgt(_con, re.sub(r"^DGT:", "", ident, flags=re.I), parte)
    except Exception as e:
        return f"No se pudo obtener el documento {ident} ({type(e).__name__}: {e})."


@mcp.tool()
def novedades_boe(desde: str, hasta: str | None = None) -> str:
    """Disposiciones con contenido tributario publicadas en el BOE entre dos fechas (máx. 31 días).

    Args:
        desde: AAAA-MM-DD.
        hasta: AAAA-MM-DD (por defecto, hoy).
    """
    try:
        return boe.novedades(desde, hasta)
    except Exception as e:
        return f"No se pudo consultar el sumario del BOE ({type(e).__name__}: {e})."


def main() -> None:
    """stdio por defecto (OpenCode, Hermes, LM Studio…).

    --http [--port 8000]: Streamable HTTP en http://127.0.0.1:8000/mcp (Open WebUI, conectores remotos).
    --publico: desactiva la protección DNS-rebinding para poder exponerlo tras un túnel HTTPS.
    """
    import argparse

    from mcp.server.transport_security import TransportSecuritySettings

    ap = argparse.ArgumentParser(prog="python -m normativa_mcp")
    ap.add_argument("--http", action="store_true", help="servir por Streamable HTTP en vez de stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--publico", action="store_true", help="aceptar cualquier Host (para túneles)")
    a = ap.parse_args()
    if not a.http:
        mcp.run("stdio")
        return
    seguridad = TransportSecuritySettings(enable_dns_rebinding_protection=False) if a.publico else None
    mcp.run("streamable-http", host=a.host, port=a.port, stateless_http=True, json_response=True,
            transport_security=seguridad)
