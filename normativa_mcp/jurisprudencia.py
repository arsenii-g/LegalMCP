"""Consulta individual de sentencias del buscador público del CENDOJ."""

from datetime import date
from html import unescape
import re
import sqlite3
import subprocess

import requests

from .doctrina import UA, _cache_get, _cache_put, _limpio, comprobar_privacidad, paginar

BASE = "https://www.poderjudicial.es/search/"
ORGANOS = {"TS": "11|12|13|14|15|16", "AN": "22|2264|23|24", "TSJ": "31|31201202|33|34"}
SALAS = {"civil": "11", "penal": "12", "contencioso": "13", "social": "14"}
DOCUMENTO = r"AN/openC?Document/[a-fA-F0-9]{16,64}/\d{8}"


def _sesion():
    s = requests.Session()
    try:
        s.headers.update(UA)
        s.get(BASE + "indexAN.jsp", timeout=30).raise_for_status()
        s.headers.update({"Referer": BASE + "indexAN.jsp", "X-Requested-With": "XMLHttpRequest"})
        return s
    except requests.RequestException:
        s.close()
        raise


def _resultados(h):
    filas = []
    for bloque in re.split(r'<div class="title">', h)[1:]:
        enlace = re.search(r'<a href="(' + re.escape(BASE) + '(' + DOCUMENTO + r'))"[^>]*data-roj="([^"]+)"[^>]*>(.*?)</a>', bloque, re.S)
        if not enlace:
            continue
        meta = re.search(r'<div class="metadatos">(.*?)</div>', bloque, re.S)
        resumen = re.search(r'<div class="summary"[^>]*>(.*?)</div>', bloque, re.S)
        filas.append(dict(url=enlace[1], id=enlace[2], roj=unescape(enlace[3]),
                          titulo=_limpio(enlace[4]), meta=_limpio(meta[1]) if meta else "",
                          resumen=_limpio(resumen[1])[:600] if resumen else ""))
    if not filas and not re.search(r'\b0 resultados|no se han encontrado|sin resultados', _limpio(h), re.I):
        raise ValueError("CENDOJ no devolvió una lista reconocible. Puede requerir verificación manual.")
    return filas


def _buscar(s, campos, limite):
    params = dict(action="query", databasematch="AN", start=1, recordsPerPage=limite,
                  TIPORESOLUCION="SENTENCIA", tab="AN", **campos)
    r = s.post(BASE + "search.action", data=params, timeout=75)
    r.raise_for_status()
    return _resultados(r.text)


def _error(exc):
    if isinstance(exc, requests.Timeout):
        return "CENDOJ no respondió dentro del plazo de espera."
    if isinstance(exc, requests.HTTPError):
        return f"CENDOJ devolvió HTTP {exc.response.status_code}. Consulte el buscador oficial."
    if isinstance(exc, requests.RequestException):
        return "No se pudo conectar con CENDOJ."
    return str(exc)


def _privacidad(*valores):
    mensaje = comprobar_privacidad(*valores)
    if mensaje:
        return mensaje.split(".")[0] + ". Describa el caso sin datos identificativos antes de consultar CENDOJ."


def _cabecera(f):
    return f"CITA: {f['titulo']}\n{f['meta']}\nFuente: {f['url']}".replace("\n", " · ")


def buscar_jurisprudencia(consulta: str, organo: str | None = "TS", jurisdiccion: str | None = "contencioso",
                          desde: str | None = None, hasta: str | None = None, max_resultados: int = 10) -> str:
    """Busca sentencias en CENDOJ por texto, órgano, jurisdicción y fechas AAAA-MM-DD."""
    bloqueo = _privacidad(consulta, organo, jurisdiccion, desde, hasta)
    if bloqueo:
        return bloqueo
    if not consulta.strip():
        return "Introduzca términos jurídicos para la búsqueda."
    org = organo.strip().upper() if organo else None
    jur = jurisdiccion.strip().lower() if jurisdiccion else None
    comunidad = None
    if org and org.startswith(("TSJ ", "TSJ:")):
        comunidad = org[4:].strip()
        if not re.fullmatch(r"[A-ZÁÉÍÓÚÜÑÀÈÏÇ][A-ZÁÉÍÓÚÜÑÀÈÏÇ -]{1,60}", comunidad):
            return "Comunidad no válida. Ejemplo: TSJ País Vasco."
        org = "TSJ"
    if org and org not in ORGANOS:
        return "Órgano no reconocido. Use TS, AN o TSJ."
    if jur and jur not in SALAS:
        return "Jurisdicción no reconocida. Use contencioso, penal, civil o social."
    campos = {"TEXT": consulta.strip()}
    if org:
        campos["TIPOORGANOPUB"] = SALAS[jur] if org == "TS" and jur else ORGANOS[org]
    if comunidad:
        campos["VALUESCOMUNIDAD"] = comunidad + "(C) | "
    if jur:
        campos["JURISDICCION"] = jur.upper()
    for clave, valor in (("FECHARESOLUCIONDESDE", desde), ("FECHARESOLUCIONHASTA", hasta)):
        if valor:
            try:
                fecha = date.fromisoformat(valor)
                if valor != fecha.isoformat():
                    raise ValueError()
            except ValueError:
                return "Fecha no válida. Use AAAA-MM-DD."
            campos[clave] = fecha.strftime("%d/%m/%Y")
    if desde and hasta and desde > hasta:
        return "La fecha inicial es posterior a la final."
    if not 1 <= max_resultados <= 50:
        return "Indique entre 1 y 50 resultados."
    try:
        with _sesion() as s:
            filas = _buscar(s, campos, next(n for n in (10, 20, 30, 50) if n >= max_resultados))
    except (requests.RequestException, ValueError) as exc:
        return _error(exc)
    return "\n\n".join(f"- id: {f['id']}\n{_cabecera(f)}\n{f['resumen']}" for f in filas[:max_resultados]) or "Sin resultados en CENDOJ."


def obtener_sentencia(con: sqlite3.Connection, id: str, parte: int = 1) -> str:
    """Lee y pagina una sentencia oficial por ROJ, ECLI, identificador CENDOJ o id de búsqueda."""
    ident = id.strip()
    if re.fullmatch(DOCUMENTO, ident):
        url = BASE + ident
    elif re.fullmatch(r"\d{20}", ident):
        url = BASE + "contenidos.action?action=getdocumentpdf&databasematch=*&idcendoj=" + ident + "&tab=AN"
    else:
        url = None
        ident = " ".join(ident.upper().split())
        if not re.fullmatch(r"ECLI:ES:[A-Z0-9]+:\d{4}:[A-Z0-9.]+|S[A-ZÑ ]{1,12} \d+/\d{4}", ident):
            return "Identificador no válido. Use el ROJ, ECLI, identificador CENDOJ o id del resultado."
    clave = "CENDOJ:" + ident
    datos = _cache_get(con, clave)
    if not datos:
        try:
            with _sesion() as s:
                if not url:
                    campo = "ECLI" if ident.startswith("ECLI:") else "ROJ"
                    filas = _buscar(s, {campo: ident}, 10)
                    fila = next((f for f in filas if ident in (f["roj"], *f["meta"].splitlines())), None)
                    if not fila:
                        return "No se ha encontrado la referencia exacta en CENDOJ."
                    url = fila["url"]
                    datos = _cache_get(con, "CENDOJ:" + fila["id"])
                if not datos:
                    r = s.get(url, timeout=75)
                    r.raise_for_status()
                    if not r.content.startswith(b"%PDF-"):
                        return "CENDOJ no entregó el PDF de la sentencia. Consulte el enlace oficial."
                    pdf = subprocess.run(["pdftotext", "-enc", "UTF-8", "-nopgbrk", "-", "-"], input=r.content,
                                         capture_output=True, timeout=45, check=True)
                    cuerpo = pdf.stdout.decode().strip()
                    roj = re.search(r"Roj:\s*(.*?)\s*-\s*(ECLI:ES:\S+)", cuerpo, re.I)
                    if not roj:
                        return "El PDF no contiene una cabecera ROJ/ECLI reconocible."
                    def campo_pdf(nombre):
                        m = re.search(r"^" + nombre + r":\s*([^\n]+)", cuerpo, re.M)
                        return m[1].strip() if m else ""
                    datos = dict(texto=cuerpo, cita=f"CITA: {roj[1]}, {campo_pdf('Fecha')} ({roj[2]}). "
                                 f"{campo_pdf('Órgano')}. Fuente: {url}")
                    for alias in (roj[1], roj[2], url.removeprefix(BASE), campo_pdf('Id Cendoj')):
                        if alias:
                            _cache_put(con, "CENDOJ:" + alias, "CENDOJ", datos)
            _cache_put(con, clave, "CENDOJ", datos)
        except (requests.RequestException, ValueError) as exc:
            return _error(exc)
        except FileNotFoundError:
            return "Se necesita pdftotext para leer el PDF de CENDOJ."
        except subprocess.SubprocessError:
            return "No se pudo extraer el texto del PDF de CENDOJ."
    return datos["cita"] + "\n\n" + paginar(datos["texto"], parte)
