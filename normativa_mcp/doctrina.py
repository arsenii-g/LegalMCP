"""Doctrina administrativa: consultas de la DGT (buscador PETETE) y criterios de los TEA (DYCTEA).

Ninguno de los dos tiene API oficial; se usan los mismos endpoints que sus buscadores web públicos.
Las búsquedas salen a internet (servidores de Hacienda), por eso se bloquean consultas con datos
identificativos. Los documentos ya leídos se guardan en la caché local.
"""

import html
import json
import re
import sqlite3
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (normativa-tributaria-mcp/0.1)"}

DGT = "https://petete.tributos.hacienda.gob.es/consultas"
TEAC = "https://serviciostelematicosext.hacienda.gob.es/TEAC/DYCTEA"

# ---------------------------------------------------------------- privacidad

_PATRONES_SENSIBLES = [
    (re.compile(r"\b\d{8}[A-HJ-NP-TV-Z]\b", re.I), "un DNI/NIF"),
    (re.compile(r"\b[XYZ]\d{7}[A-Z]\b", re.I), "un NIE"),
    (re.compile(r"\b[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]\b", re.I), "un CIF/NIF de entidad"),
    (re.compile(r"\bES\d{2}[\s\d]{20,}\b", re.I), "un IBAN"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "un correo electrónico"),
    (re.compile(r"\b(?:\+34|0034)?\s?[6789]\d{2}\s?\d{3}\s?\d{3}\b"), "un teléfono"),
]


def comprobar_privacidad(*textos: str | None) -> str | None:
    for t in textos:
        if not t:
            continue
        for patron, que in _PATRONES_SENSIBLES:
            if patron.search(t):
                return (f"BLOQUEADO: la búsqueda contiene {que}. Las búsquedas de doctrina se envían a los "
                        "servidores de Hacienda; describa el caso solo con términos jurídicos, sin datos del cliente.")
    return None


# ---------------------------------------------------------------- utilidades

def _limpio(fragmento_html: str) -> str:
    t = re.sub(r"\s+", " ", fragmento_html)
    t = re.sub(r"<br\s*/?>|</p>|</tr>|</li>|</h\d>|</div>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return "\n".join(line.strip() for line in t.split("\n")).strip()


def _cache_get(con: sqlite3.Connection, clave: str) -> dict | None:
    fila = con.execute("SELECT contenido FROM cache WHERE clave=?", (clave,)).fetchone()
    return json.loads(fila["contenido"]) if fila else None


def _cache_put(con: sqlite3.Connection, clave: str, fuente: str, datos: dict) -> None:
    with con:
        con.execute("INSERT OR REPLACE INTO cache(clave,fuente,contenido) VALUES (?,?,?)",
                    (clave, fuente, json.dumps(datos, ensure_ascii=False)))


def paginar(texto: str, parte: int, tam: int = 12000) -> str:
    total = max(1, -(-len(texto) // tam))
    parte = min(max(1, parte), total)
    trozo = texto[(parte - 1) * tam: parte * tam]
    if total > 1:
        trozo += f"\n\n[Parte {parte} de {total}. Pida parte={parte + 1} para continuar.]" if parte < total \
            else f"\n\n[Parte {parte} de {total}. Fin del documento.]"
    return trozo


# ================================================================ DGT

def _dgt_fecha(f: str | None) -> str:
    if not f:
        return ""
    from .boe import fecha_iso
    i = fecha_iso(f)
    return f"{i[6:8]}/{i[4:6]}/{i[0:4]}"


def _dgt_params(texto=None, normativa=None, numero=None, desde=None, hasta=None) -> dict:
    p = {"cmpOrder": "FECHA-SALIDA", "dirOrder": "1"}
    campos = [("NUM-CONSULTA", numero), ("FECHA-SALIDA", None), ("NORMATIVA", normativa),
              ("CUESTION-PLANTEADA", None), ("DESCRIPCION-HECHOS", None), ("FreeText", texto)]
    for i, (nombre, valor) in enumerate(campos, 1):
        p[f"NMCMP_{i}"] = nombre
        p[f"OPCMP_{i}"] = ".Y"
        p[f"VLCMP_{i}"] = valor or ""
    if desde or hasta:
        d, h = _dgt_fecha(desde) or "01/01/1990", _dgt_fecha(hasta)
        p["VLCMP_2"] = f"{d}..{h}" if h else d
    return p


def _dgt_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({**UA, "X-Requested-With": "XMLHttpRequest", "Referer": f"{DGT}/"})
    s.get(f"{DGT}/", timeout=30)
    return s


def _dgt_parse_resultados(h: str) -> tuple[int, list[dict]]:
    m = re.search(r'updateNumResults\("\d",\s*"(\d+)"\)', h)
    total = int(m.group(1)) if m else 0
    res = []
    for td in re.finditer(r'<td id="doc_(\d+)".*?</td>', h, re.S):
        bloque = td.group(0)
        def campo(clase):
            mm = re.search(rf'<span class="{clase}">(.*?)</span>', bloque, re.S)
            return _limpio(mm.group(1)) if mm else ""
        res.append({"doc": td.group(1), "numero": campo("NUM-CONSULTA"),
                    "hechos": campo("DESCRIPCION-HECHOS"), "cuestion": campo("CUESTION-PLANTEADA")})
    return total, res


def buscar_dgt(consulta: str, tipo: str = "vinculantes", normativa: str | None = None,
               desde: str | None = None, hasta: str | None = None, max_resultados: int = 10) -> str:
    bloqueo = comprobar_privacidad(consulta, normativa)
    if bloqueo:
        return bloqueo
    s = _dgt_sesion()
    base = _dgt_params(texto=consulta, normativa=normativa, desde=desde, hasta=hasta)
    pestañas = {"generales": [("1", "type1")], "vinculantes": [("2", "type2")],
                "ambas": [("2", "type2"), ("1", "type1")]}.get(tipo, [("2", "type2")])
    salida = []
    for tab, campo_tipo in pestañas:
        params = {**base, campo_tipo: "on", "tab": tab, "page": "1"}
        r = s.get(f"{DGT}/do/search", params=params, timeout=60)
        if r.status_code == 400:
            return "La DGT rechaza la sintaxis de la búsqueda (caracteres no permitidos o solo palabras vacías)."
        r.raise_for_status()
        total, res = _dgt_parse_resultados(r.text)
        nombre = "vinculantes" if tab == "2" else "generales"
        salida.append(f"Consultas {nombre} de la DGT para «{consulta}»: {total} encontradas "
                      f"(se muestran {min(total, max_resultados)}, las más recientes primero).")
        for x in res[:max_resultados]:
            salida.append(f"\n- {x['numero']}\n  Hechos: {x['hechos'][:500]}\n  Cuestión: {x['cuestion'][:500]}")
    salida.append("\nUse obtener_documento('<número>') para leer la contestación completa antes de citarla. "
                  "Si hay demasiados resultados, añada términos o filtre por 'normativa' (p. ej. 'Ley 37/1992 art. 104').")
    return "\n".join(salida)


def obtener_dgt(con: sqlite3.Connection, numero: str, parte: int = 1) -> str:
    numero = numero.strip().upper()
    clave = f"DGT:{numero}"
    datos = _cache_get(con, clave)
    if not datos:
        s = _dgt_sesion()
        tab, campo_tipo = ("2", "type2") if numero.startswith("V") else ("1", "type1")
        params = {**_dgt_params(numero=numero), campo_tipo: "on"}
        r = s.get(f"{DGT}/do/search", params={**params, "tab": tab, "page": "1"}, timeout=60)
        r.raise_for_status()
        _, res = _dgt_parse_resultados(r.text)
        res = [x for x in res if x["numero"].upper() == numero] or res[:1]
        if not res:
            return f"No encuentro la consulta {numero} en la DGT."
        time.sleep(0.3)
        r = s.get(f"{DGT}/do/document", params={**params, "doc": res[0]["doc"], "tab": tab}, timeout=60)
        r.raise_for_status()
        datos = {}
        for fila in re.finditer(r'<tr class="([A-Z\-]+)">\s*<th[^>]*>(.*?)</th>\s*<td class="value">(.*?)</td>', r.text, re.S):
            datos[_limpio(fila.group(2))] = _limpio(fila.group(3))
        if not datos:
            return f"No he podido leer el documento de la consulta {numero}."
        datos["_url"] = f"{DGT}/?num_consulta={numero}"
        _cache_put(con, clave, "DGT", datos)
    url = datos.pop("_url", DGT)
    cuerpo = "\n\n".join(f"### {k}\n{v}" for k, v in datos.items())
    cabecera = (f"# Consulta {'vinculante ' if numero.startswith('V') else ''}DGT {numero}\n"
                f"CITA: Consulta {'vinculante ' if numero.startswith('V') else ''}de la DGT {numero}, "
                f"de {datos.get('Fecha salida', 'fecha desconocida')} ({datos.get('Órgano', '')}). Fuente: {url}\n")
    return paginar(cabecera + "\n" + cuerpo, parte)


# ================================================================ TEAC (DYCTEA)

def buscar_teac(consulta: str, solo_doctrina: bool = False, desde: str | None = None,
                hasta: str | None = None, max_resultados: int = 10) -> str:
    bloqueo = comprobar_privacidad(consulta)
    if bloqueo:
        return bloqueo
    params = {"s": "1", "rs": "", "rn": "", "ra": "", "fd": _dgt_fecha(desde), "fh": _dgt_fecha(hasta),
              "u": "", "n": "", "p": "", "c1": "", "c2": "", "c3": "", "tc": "1", "tr": "1",
              "tp": consulta, "tf": "", "c": "0" if solo_doctrina else "2", "pg": "1"}
    r = requests.get(f"{TEAC}/criterios.aspx", params=params, headers=UA, timeout=60)
    r.raise_for_status()
    m = re.search(r"Se han obtenido (\d+) resultados", r.text)
    total = int(m.group(1)) if m else 0
    items = re.findall(
        r"<li class='resultadoCriterio'>.*?href='criterio\.aspx\?id=([^&']+).*?'>(.*?)</a>.*?"
        r"<span class='resultadoCriterioTexto'>(.*?)</span>", r.text, re.S)
    if not items:
        return f"Sin resultados en DYCTEA (TEAC/TEAR) para «{consulta}»."
    salida = [f"Criterios de los Tribunales Económico-Administrativos para «{consulta}»: {total} resultados "
              f"({'solo doctrina vinculante' if solo_doctrina else 'todos'}; se muestran {min(len(items), max_resultados)})."]
    for ident, titulo, texto in items[:max_resultados]:
        salida.append(f"\n- id: TEAC:{html.unescape(ident)}\n  {_limpio(titulo)}\n  {_limpio(texto)[:600]}")
    salida.append("\nUse obtener_documento('TEAC:<id>') para leer el criterio completo y, si hace falta, "
                  "obtener_documento('TEAC:<id>', texto_completo=True) para la resolución entera.")
    return "\n".join(salida)


def obtener_teac(con: sqlite3.Connection, ident: str, texto_completo: bool = False, parte: int = 1) -> str:
    ident = ident.strip()
    clave = f"TEAC:{ident}" + (":texto" if texto_completo else "")
    datos = _cache_get(con, clave)
    url = f"{TEAC}/criterio.aspx?id={ident}"
    if not datos:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        datos = {}
        for campo, nombre in [("Titulo", "Criterio"), ("Calificacion", "Calificación"), ("Unidad", "Unidad resolutoria"),
                              ("Fecha", "Fecha de la resolución"), ("Asunto", "Asunto"), ("Contenido", "Criterio"),
                              ("Normas", "Referencias normativas"), ("Conceptos", "Conceptos")]:
            m = re.search(rf"<div id='criterioDatos{campo}'[^>]*>(.*?)</div>", r.text, re.S)
            if m:
                valor = _limpio(m.group(1))
                valor = re.sub(rf"^{nombre}:\s*", "", valor).strip()
                datos[nombre if campo != "Titulo" else "Identificación"] = valor
        if not datos:
            return f"No encuentro el criterio {ident} en DYCTEA."
        if texto_completo:
            r2 = requests.get(f"{TEAC}/textoresolucion.aspx?id={ident}", headers=UA, timeout=90)
            r2.raise_for_status()
            cuerpo = re.sub(r"<style.*?</style>", "", r2.text, flags=re.S | re.I)
            datos["Texto de la resolución"] = _limpio(cuerpo)
        _cache_put(con, clave, "TEAC", datos)
    ident_res = re.search(r"resolución:\s*(\S+)", datos.get("Identificación", ""))
    cabecera = (f"# {datos.get('Unidad resolutoria', 'TEA')} — resolución "
                f"{ident_res.group(1) if ident_res else ident}\n"
                f"CITA: Resolución del {datos.get('Unidad resolutoria', 'TEA')} de "
                f"{datos.get('Fecha de la resolución', '')}, RG {ident_res.group(1) if ident_res else ident} "
                f"({datos.get('Calificación', '')}). Fuente: {url}\n")
    cuerpo = "\n\n".join(f"### {k}\n{v}" for k, v in datos.items())
    return paginar(cabecera + "\n" + cuerpo, parte)
