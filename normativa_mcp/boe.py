"""Normativa consolidada del BOE: descarga, indexado y consulta.

API usada (datos abiertos del BOE, sin clave):
  GET https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ID}/metadatos   (JSON)
  GET https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ID}/texto       (XML)
El /texto trae TODOS los bloques (artículos, disposiciones, encabezados) con TODAS sus
versiones históricas (<version fecha_vigencia=…>). Eso permite pedir la redacción vigente
en cualquier fecha sin depender de internet.
"""

import datetime as dt
import re
import sqlite3
import time
import xml.etree.ElementTree as ET

import requests

from . import texto as tx
from .catalogo import NORMAS

API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"
UA = {"User-Agent": "normativa-tributaria-mcp/0.1"}

_NIVELES = {"libro": 0, "titulo": 1, "capitulo": 2, "seccion": 3, "subseccion": 4}


# ================================================================ descarga

def metadatos(boe_id: str) -> dict:
    r = requests.get(f"{API}/id/{boe_id}/metadatos", headers={**UA, "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    return r.json()["data"][0]


def _corto(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def _texto_elem(el: ET.Element) -> tuple[list[str], list[str]]:
    """Convierte el contenido de una <version> en (párrafos, notas de modificación)."""
    parrafos, notas = [], []
    for hijo in el:
        tag = hijo.tag.lower()
        if tag == "blockquote":
            for p in hijo.iter():
                if p.tag == "p":
                    t = " ".join("".join(p.itertext()).split())
                    if t:
                        notas.append(t)
        elif tag == "table":
            for fila in hijo.iter("tr"):
                celdas = [" ".join("".join(c.itertext()).split()) for c in fila if c.tag in ("td", "th")]
                if any(celdas):
                    parrafos.append(" | ".join(celdas))
        else:
            t = " ".join("".join(hijo.itertext()).split())
            if t:
                parrafos.append(t)
    return parrafos, notas


def descargar_norma(con: sqlite3.Connection, alias: str, forzar: bool = False) -> str:
    boe_id, nombre = NORMAS[alias]
    meta = metadatos(boe_id)
    previa = con.execute("SELECT fecha_actualizacion FROM normas WHERE alias=?", (alias,)).fetchone()
    if previa and previa["fecha_actualizacion"] == meta["fecha_actualizacion"] and not forzar:
        return f"{alias}: sin cambios (BOE actualizado {meta['fecha_actualizacion']})"

    r = requests.get(f"{API}/id/{boe_id}/texto", headers={**UA, "Accept": "application/xml"}, timeout=300)
    r.raise_for_status()
    raiz = ET.fromstring(r.content)

    with con:
        viejos = [f["id"] for f in con.execute(
            "SELECT v.id FROM versiones v JOIN bloques b ON b.id=v.bloque_pk WHERE b.alias=?", (alias,))]
        con.executemany("DELETE FROM versiones_fts WHERE rowid=?", [(i,) for i in viejos])
        con.execute("DELETE FROM versiones WHERE bloque_pk IN (SELECT id FROM bloques WHERE alias=?)", (alias,))
        con.execute("DELETE FROM bloques WHERE alias=?", (alias,))

        ruta: list[str | None] = [None] * len(_NIVELES)
        n_bloques = n_versiones = 0
        for orden, bloque in enumerate(raiz.iter("bloque")):
            tipo = bloque.get("tipo", "")
            titulo = bloque.get("titulo", "") or ("Preámbulo" if tipo == "preambulo" else bloque.get("id"))
            versiones = sorted(bloque.findall("version"), key=lambda v: v.get("fecha_vigencia") or "")

            if tipo == "encabezado":
                nivel = _NIVELES.get(tx.clave(titulo.split()[0]) if titulo else "", 0)
                p, _ = _texto_elem(versiones[-1]) if versiones else ([], [])
                ruta[nivel] = ". ".join(p) if p else titulo
                for k in range(nivel + 1, len(ruta)):
                    ruta[k] = None
            elif tipo == "precepto" and re.match(r"(?i)(disposici|anexo)", titulo or ""):
                # Las disposiciones y anexos cuelgan de la norma (o del reglamento aprobado), no del último título.
                for k in range(1, len(ruta)):
                    ruta[k] = None
            ruta_txt = " > ".join(_corto(x) for x in ruta if x)
            if tipo == "precepto" and versiones and not re.match(r"[A-Za-zÁÉÍÓÚáéíóú]", titulo or ""):
                # Normas como el PGC titulan sus bloques «15»; el nombre real está en la primera línea.
                p, _ = _texto_elem(versiones[-1])
                if p:
                    titulo = _corto(p[0], 90)

            # Los códigos Civil y de Comercio abrevian «Artículo» en los títulos de bloque.
            titulo_normalizado = re.sub(r"^Art\.?\s+(?=\d)", "Artículo ", titulo, flags=re.I)
            cur = con.execute(
                "INSERT INTO bloques(alias,bloque_id,tipo,titulo,titulo_clave,ruta,orden) VALUES (?,?,?,?,?,?,?)",
                (alias, bloque.get("id"), tipo, titulo, tx.clave(titulo_normalizado), ruta_txt, orden))
            bloque_pk = cur.lastrowid
            n_bloques += 1
            for i, v in enumerate(versiones):
                parrafos, notas = _texto_elem(v)
                hasta = versiones[i + 1].get("fecha_vigencia") if i + 1 < len(versiones) else None
                texto = "\n".join(parrafos)
                cur = con.execute(
                    "INSERT INTO versiones(bloque_pk,id_norma,fecha_publicacion,fecha_vigencia,fecha_hasta,texto,notas)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (bloque_pk, v.get("id_norma"), v.get("fecha_publicacion"), v.get("fecha_vigencia") or None, hasta,
                     texto, "\n".join(notas)))
                if tipo in ("precepto", "preambulo") or (tipo == "encabezado" and len(texto) > 300):
                    con.execute("INSERT INTO versiones_fts(rowid,titulo,ruta,texto) VALUES (?,?,?,?)",
                                (cur.lastrowid, tx.texto_indexable(titulo), tx.texto_indexable(ruta_txt),
                                 tx.texto_indexable(texto)))
                n_versiones += 1

        con.execute(
            "INSERT OR REPLACE INTO normas VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
            (alias, boe_id, nombre, meta.get("titulo"), (meta.get("rango") or {}).get("texto"),
             meta.get("numero_oficial"), meta.get("url_eli"), meta.get("url_html_consolidada"),
             (meta.get("estado_consolidacion") or {}).get("texto"), meta.get("fecha_actualizacion")))
    return f"{alias}: {n_bloques} bloques, {n_versiones} versiones (BOE actualizado {meta['fecha_actualizacion']})"


def descargar_todo(con: sqlite3.Connection, solo: list[str] | None = None, forzar: bool = False):
    for alias in solo or list(NORMAS):
        try:
            yield descargar_norma(con, alias, forzar)
        except Exception as e:  # una norma que falla no debe parar el resto
            yield f"{alias}: ERROR {type(e).__name__}: {e}"
        time.sleep(0.5)


# ================================================================ consulta

def fecha_iso(f: str | None) -> str:
    """'2021-07-11', '11/07/2021' o '20210711' -> '20210711'. Vacío -> hoy."""
    if not f:
        return dt.date.today().strftime("%Y%m%d")
    f = f.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(f, fmt).strftime("%Y%m%d")
        except ValueError:
            pass
    raise ValueError(f"Fecha no válida: {f!r}. Use AAAA-MM-DD o DD/MM/AAAA.")


def fmt_fecha(f: str | None) -> str:
    return f"{f[6:8]}/{f[4:6]}/{f[0:4]}" if f and len(f) == 8 else "—"


def _aviso_consolidacion(norma: sqlite3.Row) -> str:
    estado = (norma["estado_consolidacion"] or "").lower()
    if estado and estado != "finalizado":
        return (f"\n⚠ El BOE marca esta norma como «{norma['estado_consolidacion']}»: puede haber modificaciones "
                f"recientes todavía no incorporadas al texto consolidado. Compruébelo en {norma['url_html']}")
    return ""


def cita(norma: sqlite3.Row, bloque: sqlite3.Row, version: sqlite3.Row) -> str:
    modif = ""
    if version["id_norma"] and version["id_norma"] != norma["boe_id"]:
        modif = f", redacción dada por {version['id_norma']}"
    return (f"{bloque['titulo']}, {norma['nombre']} [{norma['alias']}] "
            f"(versión vigente desde {fmt_fecha(version['fecha_vigencia'])}{modif}). "
            f"Fuente: {norma['url_html']}#{bloque['bloque_id']}")


_NUM_APARTADO = (r"(?:\d+|Uno|Dos|Tres|Cuatro|Cinco|Seis|Siete|Ocho|Nueve|Diez|Once|Doce|Trece|Catorce|Quince|"
                 r"Dieciséis|Diecisiete|Dieciocho|Diecinueve|Veinte)")


def recortar_apartado(texto: str, apartado: str) -> str | None:
    """Devuelve la primera línea (título) y solo el apartado pedido («6», «Dos»…), o None si no existe."""
    lineas = texto.split("\n")
    inicio = re.compile(rf"^{re.escape(apartado.strip().rstrip('.'))}\.\s", re.I)
    otro = re.compile(rf"^{_NUM_APARTADO}\.\s", re.I)
    for i, l in enumerate(lineas):
        if inicio.match(l):
            fin = next((j for j in range(i + 1, len(lineas)) if otro.match(lineas[j])), len(lineas))
            return "\n".join([lineas[0], "[…]"] + lineas[i:fin] + (["[…]"] if fin < len(lineas) else []))
    return None


def obtener_articulo(con: sqlite3.Connection, alias: str, articulo: str, fecha: str | None,
                     apartado: str | None = None) -> str:
    norma = con.execute("SELECT * FROM normas WHERE alias=?", (alias,)).fetchone()
    if not norma:
        return f"La norma {alias} no está descargada. Ejecute la actualización (python -m normativa_mcp.ingest)."
    f = fecha_iso(fecha)
    claves = tx.claves_articulo(articulo)
    bloques = con.execute(
        f"SELECT * FROM bloques WHERE alias=? AND (titulo_clave IN ({','.join('?' * len(claves))}) OR bloque_id=?)"
        " ORDER BY orden", (alias, *claves, articulo.strip().lstrip("#"))).fetchall()
    if not bloques and len(tx.clave(articulo)) >= 1:
        # p. ej. PGC: «15» -> «15.ª Provisiones y contingencias», «15.ª Partes vinculadas»…
        bloques = con.execute(
            "SELECT * FROM bloques WHERE alias=? AND titulo_clave LIKE ? AND tipo <> 'preambulo' ORDER BY orden LIMIT 5",
            (alias, tx.clave(articulo) + "%")).fetchall()
    if not bloques:
        pref = re.sub(r"(bis|ter|quater|quinquies|sexies)$", "", claves[0])
        parecidos = [b["titulo"] for b in con.execute(
            "SELECT titulo FROM bloques WHERE alias=? AND titulo_clave LIKE ? AND tipo='precepto' ORDER BY orden LIMIT 8",
            (alias, pref + "%"))]
        extra = f" Preceptos parecidos: {', '.join(parecidos)}." if parecidos else ""
        return f"No encuentro «{articulo}» en {norma['nombre']}.{extra}"

    salida = []
    for b in bloques:
        versiones = con.execute("SELECT * FROM versiones WHERE bloque_pk=? ORDER BY fecha_vigencia", (b["id"],)).fetchall()
        v = next((x for x in versiones if x["fecha_vigencia"] and x["fecha_vigencia"] <= f and (not x["fecha_hasta"] or x["fecha_hasta"] > f)), None)
        historial = "; ".join(
            f"desde {fmt_fecha(x['fecha_vigencia'])}" + (f" ({x['id_norma']})" if x["id_norma"] != norma["boe_id"] else " (original)")
            for x in versiones)
        if v is None:
            salida.append(f"{b['titulo']} ({b['ruta']}): no estaba vigente el {fmt_fecha(f)}. "
                          f"Versiones disponibles: {historial}")
            continue
        hasta = f" hasta {fmt_fecha(v['fecha_hasta'])} (excluido)" if v["fecha_hasta"] else " (redacción actual)"
        cuerpo = v["texto"] or "(sin texto)"
        if apartado:
            recorte = recortar_apartado(cuerpo, apartado)
            cuerpo = recorte if recorte else f"(No encuentro el apartado {apartado}; se muestra el artículo completo.)\n{cuerpo}"
        partes = [
            f"## {b['titulo']} — {norma['nombre']}",
            f"Ubicación: {b['ruta'] or '—'}",
            f"Redacción consultada: vigente a {fmt_fecha(f)} → aplicable desde {fmt_fecha(v['fecha_vigencia'])}{hasta}",
            "",
            cuerpo,
        ]
        if v["notas"]:
            partes += ["", "Notas de modificación (BOE):", v["notas"]]
        partes += ["", f"Historial de redacciones: {historial}", f"CITA: {cita(norma, b, v)}"]
        salida.append("\n".join(partes))
    return "\n\n---\n\n".join(salida) + _aviso_consolidacion(norma)


def _fts_query(terminos: list[str], operador: str) -> str:
    return f" {operador} ".join(f'"{t}"' for t in terminos)


def _fragmento(texto: str, terminos: set[str], max_chars: int = 450) -> str:
    parrafos = [p for p in texto.split("\n") if p.strip()]
    if not parrafos:
        return ""
    def puntos(i: int) -> float:
        p = len(terminos & set(tx.stems(parrafos[i])))
        return p - 0.5 if i == 0 and re.match(r"(Artículo|Disposición)", parrafos[i]) else p

    puntuados = sorted(range(len(parrafos)), key=lambda i: -puntos(i))
    elegidos = sorted(puntuados[:2])
    frag = " […] ".join(parrafos[i] for i in elegidos)
    return frag if len(frag) <= max_chars else frag[:max_chars] + "…"


def buscar(con: sqlite3.Connection, consulta: str, alias: str | None, fecha: str | None,
           max_resultados: int = 5, incluir_preambulo: bool = False) -> str:
    terminos = list(dict.fromkeys(tx.stems(consulta)))
    if not terminos:
        return "La consulta no contiene términos útiles. Reformúlela con palabras clave."
    f = fecha_iso(fecha)
    filtros = ["v.fecha_vigencia <= ?", "(v.fecha_hasta IS NULL OR v.fecha_hasta > ?)"]
    params: list = [f, f]
    if alias:
        filtros.append("b.alias = ?")
        params.append(alias)
    if not incluir_preambulo:
        filtros.append("b.tipo <> 'preambulo'")
    sql = (
        "SELECT b.*, v.id AS vid, v.texto, v.fecha_vigencia, v.fecha_hasta, v.id_norma, v.notas, "
        "bm25(versiones_fts, 4.0, 1.5, 1.0) AS score "
        "FROM versiones_fts JOIN versiones v ON v.id = versiones_fts.rowid JOIN bloques b ON b.id = v.bloque_pk "
        f"WHERE versiones_fts MATCH ? AND {' AND '.join(filtros)} ORDER BY score LIMIT ?")

    vistos, filas = set(), []
    for op in ("AND", "OR"):  # primero todos los términos; si hay pocos resultados, cualquiera
        for fila in con.execute(sql, (_fts_query(terminos, op), *params, max_resultados)):
            if fila["vid"] not in vistos:
                vistos.add(fila["vid"])
                filas.append(fila)
        if len(filas) >= max_resultados or len(terminos) == 1:
            break
    filas = filas[:max_resultados]
    if not filas:
        return "Sin resultados en la normativa descargada. Pruebe con otros términos o sin filtrar por ley."

    normas = {n["alias"]: n for n in con.execute("SELECT * FROM normas")}
    tset = set(terminos)
    salida = [f"Resultados para «{consulta}» (redacción vigente a {fmt_fecha(f)}):"]
    for i, fila in enumerate(filas, 1):
        n = normas[fila["alias"]]
        salida.append(
            f"\n{i}. [{fila['alias']}] {fila['titulo']} — {fila['ruta'] or ''} (id: {fila['bloque_id']})\n"
            f"   {_fragmento(fila['texto'], tset)}\n"
            f"   CITA: {cita(n, fila, fila)}")
    salida.append("\nUse obtener_articulo(ley, articulo, fecha) para leer el texto completo antes de citarlo.")
    return "\n".join(salida)


def listar_normas(con: sqlite3.Connection) -> str:
    filas = {n["alias"]: n for n in con.execute("SELECT * FROM normas")}
    lineas = ["Normas disponibles (alias → norma):"]
    for alias, (boe_id, nombre) in NORMAS.items():
        n = filas.get(alias)
        estado = (f"descargada, BOE actualizado {n['fecha_actualizacion'][:8]}, consolidación: {n['estado_consolidacion']}"
                  if n else "NO descargada")
        lineas.append(f"- {alias}: {nombre} ({boe_id}) — {estado}")
    return "\n".join(lineas)


# ================================================================ novedades (sumario diario del BOE)

_PALABRAS_FISCALES = re.compile(
    r"tribut|impuesto|fiscal|\biva\b|renta de las personas|aduan|recaudaci|"
    r"declaraci[oó]n informativa|modelo \d{3}|agencia estatal de administraci[oó]n tributaria", re.I)
_EXCLUIR = re.compile(r"ministerio fiscal|fiscal[ií]a|fiscal de sala|carrera fiscal|antes de impuestos|recursos humanos|identificaci[oó]n fiscal", re.I)


def novedades(desde: str, hasta: str | None = None) -> str:
    d0 = dt.datetime.strptime(fecha_iso(desde), "%Y%m%d").date()
    d1 = dt.datetime.strptime(fecha_iso(hasta), "%Y%m%d").date()
    if (d1 - d0).days > 31:
        return "El intervalo máximo es de 31 días."
    encontrados = []
    dia = d0
    while dia <= d1:
        r = requests.get(f"https://www.boe.es/datosabiertos/api/boe/sumario/{dia:%Y%m%d}",
                         headers={**UA, "Accept": "application/json"}, timeout=60)
        if r.status_code == 200:
            for diario in r.json()["data"]["sumario"]["diario"]:
                for sec in diario.get("seccion", []):
                    if sec.get("codigo") not in ("1", "3", "T"):  # Disp. generales, Otras disp., TC
                        continue
                    for dep in _lista(sec.get("departamento")):
                        for item in _items(dep):
                            titulo = item.get("titulo", "")
                            if _PALABRAS_FISCALES.search(titulo) and not _EXCLUIR.search(titulo):
                                encontrados.append(
                                    f"- {fmt_fecha(dia.strftime('%Y%m%d'))} [{item.get('identificador')}] {titulo}\n"
                                    f"  {_url(item)}")
        dia += dt.timedelta(days=1)
        time.sleep(0.2)
    if not encontrados:
        return f"No hay publicaciones de contenido tributario en el BOE entre {d0:%d/%m/%Y} y {d1:%d/%m/%Y}."
    return (f"Publicaciones con contenido tributario en el BOE ({d0:%d/%m/%Y}–{d1:%d/%m/%Y}):\n"
            + "\n".join(encontrados))


def _lista(x):
    return x if isinstance(x, list) else ([x] if x else [])


def _items(dep: dict):
    for it in _lista(dep.get("item")):
        yield it
    for ep in _lista(dep.get("epigrafe")):
        for it in _lista(ep.get("item")):
            yield it


def _url(item: dict) -> str:
    u = item.get("url_html")
    if isinstance(u, dict):
        u = u.get("texto")
    return u or f"https://www.boe.es/diario_boe/txt.php?id={item.get('identificador')}"
