"""Utilidades de texto: normalización, lematización ligera (Snowball) y claves de artículo."""

import re
import unicodedata

import snowballstemmer

_stemmer = snowballstemmer.stemmer("spanish")

STOPWORDS = set(
    """a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el ella
    ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha han hasta hay la las le
    les lo los mas me mi mis mucho muy nada ni no nos o os otra otras otro otros para pero poco por porque que
    quien se ser si sin sobre su sus tambien te tiene tienen todo todos tu tus un una uno unos y ya cual cuales
    articulo articulos ley norma segun puede pueden debe deben caso""".split()
)


def sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(s: str) -> list[str]:
    s = sin_acentos(s.lower())
    return re.findall(r"[a-z0-9]+", s)


def _stems(s: str, quitar_stopwords: bool) -> list[str]:
    toks = tokens(s)
    if quitar_stopwords:
        toks = [t for t in toks if t not in STOPWORDS and len(t) > 1]
    return _stemmer.stemWords(toks)


def stems(s: str, quitar_stopwords: bool = True) -> list[str]:
    """Añade a las expresiones de consulta habituales el vocabulario usado por el BOE."""
    normalizado = sin_acentos(s.lower())
    if re.search(r"\b(?:plusvalia municipal|plusvalias municipales)\b", normalizado):
        s += " incremento valor terrenos naturaleza urbana"
    if re.search(r"\bdelito fiscal\b|\bdelitos fiscales\b", normalizado):
        s += " defraude Hacienda Pública tributos"
    return _stems(s, quitar_stopwords)


def texto_indexable(s: str) -> str:
    """Texto lematizado que se guarda en el índice FTS5 (BM25)."""
    return " ".join(_stems(s, quitar_stopwords=True))


# ---------------------------------------------------------------- claves de artículo

_ORD_BASE = ["", "primera", "segunda", "tercera", "cuarta", "quinta", "sexta", "septima", "octava", "novena"]
_LATIN = {"bis": "bis", "ter": "ter", "quater": "quater", "quinquies": "quinquies", "sexies": "sexies",
          "septies": "septies", "octies": "octies", "nonies": "nonies", "decies": "decies"}


def ordinales(n: int) -> list[str]:
    """Formas (sin acentos ni espacios) con las que el BOE escribe el ordinal femenino n."""
    if n == 0:
        return []
    if n < 10:
        return [_ORD_BASE[n]]
    especiales = {10: ["decima"], 11: ["undecima", "decimoprimera"], 12: ["duodecima", "decimosegunda"],
                  20: ["vigesima"], 30: ["trigesima"], 40: ["cuadragesima"], 50: ["quincuagesima"]}
    if n in especiales:
        return especiales[n]
    decena, unidad = divmod(n, 10)
    prefijo = {1: "decimo", 2: "vigesimo", 3: "trigesimo", 4: "cuadragesimo", 5: "quincuagesimo"}.get(decena)
    if not prefijo:
        return []
    base = _ORD_BASE[unidad]
    formas = [prefijo + base]
    if base.startswith("o"):  # decimoctava
        formas.append(prefijo[:-1] + base)
    return formas


def clave(s: str) -> str:
    """Clave de comparación: minúsculas, sin acentos, solo letras y números."""
    return re.sub(r"[^a-z0-9]", "", sin_acentos(s.lower()))


_TIPOS_DISP = {
    "da": "disposicionadicional", "dt": "disposiciontransitoria", "dd": "disposicionderogatoria",
    "df": "disposicionfinal", "adicional": "disposicionadicional", "transitoria": "disposiciontransitoria",
    "derogatoria": "disposicionderogatoria", "final": "disposicionfinal",
}


def claves_articulo(entrada: str) -> list[str]:
    """Convierte '95 bis', 'art. 108', 'DA 1ª', 'disposición transitoria segunda'… en claves de título.

    Las claves se comparan con clave(titulo_del_bloque) (p. ej. 'articulo95bis', 'disposicionadicionalprimera').
    """
    e = sin_acentos(entrada.lower()).strip()
    e = e.replace("º", "").replace("ª", "")
    e = re.sub(r"\b(art(iculo)?s?|art)\.?\s*", "articulo ", e)
    e = re.sub(r"\s+", " ", e).strip()

    # Disposiciones: "da 1", "disposicion adicional 1", "disp. adicional primera", "dt 2ª"
    m = re.match(r"^(?:disp(?:osicion)?\.?\s*)?(da|dt|dd|df|adicional|transitoria|derogatoria|final)\.?\s*(.*)$", e)
    if m:
        tipo = _TIPOS_DISP[m.group(1)]
        resto = m.group(2).strip()
        if not resto:
            return [tipo + "unica"]
        num = re.match(r"^(\d+)", resto)
        if num:
            return [tipo + o for o in ordinales(int(num.group(1)))]
        return [tipo + clave(resto)]

    # Artículos: "articulo 95 bis", "95bis", "108", "articulo unico"
    m = re.match(r"^(?:articulo\s*)?(\d+)\s*([a-z]*)\s*$", e)
    if m:
        sufijo = _LATIN.get(m.group(2), m.group(2))
        return ["articulo" + m.group(1) + sufijo]
    return [clave(e) if clave(e).startswith(("articulo", "disposicion", "anexo")) else "articulo" + clave(e)]
