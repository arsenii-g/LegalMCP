"""Servidor MCP «normativa-tributaria».

Arranque (stdio, lo lanza el cliente MCP: OpenCode, Hermes, LM Studio, Claude Desktop…):
    python -m normativa_mcp
"""

import re

from mcp.server.mcpserver import MCPServer

from . import boe, calculos, doctrina, jurisprudencia
from .catalogo import NORMAS, resolver_alias
from .db import conectar

INSTRUCCIONES = """Fuente de derecho tributario español con citas verificables: normativa del BOE (con su historial de
redacciones), doctrina de la DGT y de los TEA, jurisprudencia del CENDOJ y calculadoras.
Reglas de uso:
1. No cite ningún artículo, consulta, resolución o sentencia que no haya leído con estas herramientas en esta
   conversación. Reproduzca la línea «CITA:» que devuelven.
2. Antes de citar un artículo, léalo con obtener_articulo. Si el caso es de un ejercicio pasado, pase la fecha
   del devengo o de los hechos para obtener la redacción vigente entonces. Use `apartado` en artículos largos.
3. Fechas, plazos, prescripción, duración de procedimientos, sanciones, recargos e intereses: use SIEMPRE las
   calculadoras (calcular_*). No haga estos cálculos de memoria.
4. Sea eficiente: no repita una búsqueda ni vuelva a leer lo que ya ha leído. Si dos búsquedas en una fuente no
   dan resultado útil, dígalo («no he encontrado …») y continúe con el resto de la respuesta.
5. Si no encuentra fuente, dígalo en lugar de suponer.
6. Las búsquedas de DGT, TEA y CENDOJ salen a internet: no incluya nombres, NIF ni datos del cliente."""

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

    La DGT interpreta los tributos (hechos imponibles, exenciones, deducciones…); casi nunca resuelve cuestiones de
    procedimiento (plazos de inspección, caducidad, prescripción, sanciones): para eso use buscar_resoluciones_teac
    o buscar_jurisprudencia. Use 2-4 palabras clave jurídicas, no frases.

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


@mcp.tool()
def buscar_jurisprudencia(consulta: str, organo: str | None = "TS", jurisdiccion: str | None = "contencioso",
                          desde: str | None = None, hasta: str | None = None, max_resultados: int = 10) -> str:
    """Busca sentencias en el CENDOJ (Poder Judicial, por internet). La materia tributaria está en la Sala 3ª
    (contencioso) del TS, Sección 2ª; los delitos contra la Hacienda Pública, en la Sala 2ª (penal).

    Args:
        consulta: palabras clave jurídicas, SIN datos del cliente.
        organo: «TS», «AN», «TSJ» o «TSJ <comunidad>» (p. ej. «TSJ Madrid»).
        jurisdiccion: «contencioso», «penal», «civil» o «social».
        desde, hasta: opcional, fechas de la sentencia AAAA-MM-DD.
        max_resultados: 1-50.
    """
    try:
        return jurisprudencia.buscar_jurisprudencia(consulta, organo, jurisdiccion, desde, hasta,
                                                    max(1, min(int(max_resultados), 50)))
    except Exception as e:
        return f"No se pudo consultar el CENDOJ ({type(e).__name__}: {e}). Inténtelo más tarde."


@mcp.tool()
def obtener_sentencia(id: str, parte: int = 1) -> str:
    """Texto oficial de una sentencia del CENDOJ, con su cita (ROJ, ECLI) y enlace.

    Args:
        id: ROJ («STS 1802/2012»), ECLI («ECLI:ES:TS:2012:1802»), identificador CENDOJ o el id que devuelve
            buscar_jurisprudencia.
        parte: las sentencias largas se devuelven por partes de ~12.000 caracteres.
    """
    try:
        return jurisprudencia.obtener_sentencia(_con, id, parte)
    except Exception as e:
        return f"No se pudo obtener la sentencia {id} ({type(e).__name__}: {e})."


# ---------------------------------------------------------------------------------------------- calculadoras


def _calculo(fn, *args, **kwargs) -> str:
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, TypeError) as e:
        return f"Datos no válidos: {e}"


@mcp.tool()
def calcular_plazo(fecha_notificacion: str, tipo: str | None = None, cantidad: int | None = None,
                   unidad: str | None = None, ambito: str = "administrativo",
                   festivos_adicionales: list[str] | None = None) -> str:
    """Último día de un plazo, con el cómputo paso a paso (art. 30 LPAC; arts. 46 y 128 LJCA; art. 183 LOPJ).

    Use `tipo` para los plazos habituales: reposicion, reclamacion_economico_administrativa, alzada_ordinaria,
    anulacion, extraordinario_revision, contencioso_administrativo, alegaciones_acta, alegaciones_tramite_audiencia,
    alegaciones_propuesta_sancion, requerimiento_informacion, tasacion_pericial_contradictoria, o
    pago_liquidacion (plazo de ingreso en voluntaria de una liquidación, art. 62.2 LGT).
    O un plazo libre con `cantidad` + `unidad` (dias_habiles, dias_naturales, meses, años) + `ambito`
    («administrativo» o «judicial»: este excluye agosto y del 24/12 al 6/1).

    Args:
        fecha_notificacion: fecha de notificación o publicación, AAAA-MM-DD.
        festivos_adicionales: festivos autonómicos o locales (AAAA-MM-DD) a excluir además de los nacionales.
    """
    if tipo and tipo.lower().replace(" ", "_") in ("pago_liquidacion", "pago", "ingreso"):
        return _calculo(calculos.plazo_pago_liquidacion, fecha_notificacion, festivos_adicionales)
    if tipo:
        return _calculo(calculos.plazo_recurso, tipo, fecha_notificacion, festivos_adicionales)
    if not (cantidad and unidad):
        return "Indique `tipo` o bien `cantidad` y `unidad`."

    def libre():
        d, pasos = calculos.calcular_vencimiento(fecha_notificacion, int(cantidad), unidad, ambito,
                                                 festivos_adicionales)
        return (f"## Plazo de {cantidad} {unidad} ({ambito})\n**Último día: {calculos.fd(d)}**\n\n- "
                + "\n- ".join(pasos) + "\n\n" + calculos._AVISO_FESTIVOS)
    return _calculo(libre)


@mcp.tool()
def calcular_prescripcion(tipo: str | None = None, ejercicio: int | None = None, periodo: str | None = None,
                          fecha_devengo: str | None = None, fin_plazo: str | None = None,
                          interrupciones: list[str] | None = None, fecha_referencia: str | None = None,
                          anios: int = 4) -> str:
    """Prescripción del derecho a liquidar (arts. 66-68 LGT): fin del plazo de declaración, inicio, interrupciones y
    fecha en que prescribe. Calcula el fin del plazo de declaración para:
    iva_trimestral / retenciones_trimestral (periodo «1T»…«4T»), iva_mensual (periodo «1»…«12»), irpf, patrimonio
    (ejercicio), is (ejercicio o fecha_devengo = cierre del periodo), isd_mortis_causa, isd_inter_vivos, itp
    (fecha_devengo). Para otros casos pase `fin_plazo` directamente.

    Args:
        interrupciones: fechas (AAAA-MM-DD) de actuaciones que interrumpen (art. 68 LGT). No incluya las actuaciones
            inspectoras realizadas dentro de un plazo de inspección incumplido (art. 150.6.a LGT).
        fecha_referencia: fecha «de hoy» para decir si está prescrito (por defecto, hoy). Use la del caso si la da.
        anios: 4 por defecto (art. 66 LGT).
    """
    return _calculo(calculos.prescripcion, fin_plazo, tipo, ejercicio, periodo, fecha_devengo, interrupciones,
                    fecha_referencia, anios)


@mcp.tool()
def calcular_duracion_procedimiento(tipo: str, fecha_inicio: str, dias_dilacion: int = 0, dias_suspension: int = 0,
                                    dias_extension: int = 0, fecha_referencia: str | None = None,
                                    fecha_terminacion: str | None = None) -> str:
    """Fecha de vencimiento de la duración máxima de un procedimiento y efectos de su incumplimiento.

    Args:
        tipo: inspeccion (18 meses), inspeccion_27 (27 meses, art. 150.1.b LGT), comprobacion_limitada,
            verificacion_datos, sancionador (6 meses).
        fecha_inicio: notificación del inicio, AAAA-MM-DD.
        dias_dilacion / dias_suspension / dias_extension: días que no computan o amplían el plazo (arts. 104.2 y
            150.3-5 LGT).
        fecha_referencia: «hoy» del caso. fecha_terminacion: notificación de la liquidación, si ya terminó.
    """
    return _calculo(calculos.duracion_procedimiento, tipo, fecha_inicio, dias_dilacion, dias_suspension,
                    dias_extension, fecha_referencia, fecha_terminacion)


@mcp.tool()
def calcular_sancion(base: float, articulo: str = "191", ocultacion: bool = False, medios_fraudulentos: bool = False,
                     facturas_falsas: bool = False, porcentaje_llevanza_incorrecta: float = 0.0,
                     porcentaje_retenciones_no_ingresadas: float | None = None,
                     cuantia_total_debida: float | None = None, devolucion_indebida: bool = False,
                     comision_repetida: str | None = None, reduccion: str | None = None, pronto_pago: bool = False,
                     fecha_sancion: str | None = None) -> str:
    """Califica la infracción y calcula la sanción con graduación y reducciones (arts. 187, 188 y 191-195 LGT).

    Args:
        base: base de la sanción (cuantía no ingresada / devuelta indebidamente / partidas improcedentes).
        articulo: 191 (dejar de ingresar), 192 (no presentar), 193 (devoluciones indebidas), 194, 195.
        ocultacion, medios_fraudulentos, facturas_falsas: hechos según art. 184 LGT.
        porcentaje_llevanza_incorrecta: incidencia de la llevanza incorrecta de libros sobre la base (%).
        porcentaje_retenciones_no_ingresadas: si se trata de retenciones practicadas y no ingresadas, su % sobre la base.
        cuantia_total_debida: lo que debió ingresarse en total, para el perjuicio económico (art. 187.1.b).
        comision_repetida: «leve», «grave» o «muy grave» si hay sanción firme previa en 4 años (art. 187.1.a).
        reduccion: «conformidad» (30 %) o «acuerdo» (acta con acuerdo, 65 %).
        pronto_pago: reducción del 40 % del art. 188.3 LGT.
        fecha_sancion: AAAA-MM-DD; antes del 11/07/2021 se aplican los porcentajes anteriores (50 % y 25 %).
    """
    return _calculo(calculos.calcular_sancion, base, articulo, ocultacion, medios_fraudulentos, facturas_falsas,
                    porcentaje_llevanza_incorrecta, porcentaje_retenciones_no_ingresadas, cuantia_total_debida,
                    devolucion_indebida, comision_repetida, reduccion, pronto_pago, fecha_sancion)


@mcp.tool()
def calcular_recargo(importe: float, tipo: str = "extemporaneo", fin_plazo: str | None = None,
                     fecha_presentacion: str | None = None, situacion_apremio: str | None = None) -> str:
    """Recargos de los arts. 27 y 28 LGT.

    Args:
        tipo: «extemporaneo» (presentación fuera de plazo sin requerimiento previo, art. 27: necesita fin_plazo y
            fecha_presentacion; aplica el régimen vigente en la fecha y compara con el de la Ley 11/2021) o
            «ejecutivo» (art. 28: necesita situacion_apremio = «ejecutivo» (5 %), «reducido» (10 %) u «ordinario» (20 %)).
    """
    if tipo.lower().startswith("ejec") or tipo.lower().startswith("apremio"):
        return _calculo(calculos.recargo_periodo_ejecutivo, importe, situacion_apremio or "ordinario")
    if not (fin_plazo and fecha_presentacion):
        return "Para el recargo extemporáneo indique fin_plazo y fecha_presentacion."
    return _calculo(calculos.recargo_extemporaneo, importe, fin_plazo, fecha_presentacion)


@mcp.tool()
def calcular_intereses(importe: float, desde: str, hasta: str, excluir: list[list[str]] | None = None,
                       tipo_interes: str = "demora") -> str:
    """Intereses de demora tributarios (art. 26 LGT) o interés legal del dinero, por tramos con los tipos oficiales
    de cada año (tabla de la AEAT).

    Args:
        importe: principal (cuota).
        desde: día de vencimiento del plazo (los intereses corren desde el día siguiente), AAAA-MM-DD.
        hasta: último día de devengo (pago o liquidación), AAAA-MM-DD.
        excluir: periodos sin devengo [[desde, hasta], …] (arts. 26.4 y 150.6.c LGT).
        tipo_interes: «demora» o «legal».
    """
    return _calculo(calculos.intereses_demora, importe, desde, hasta, excluir, tipo_interes)


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
