"""Catálogo de normas que se descargan del BOE (texto consolidado).

Cada entrada: alias corto -> (identificador BOE, nombre para citar).
Los identificadores están verificados contra la API de datos abiertos del BOE.
Para añadir una norma: buscar su identificador en https://www.boe.es/buscar/legislacion.php
(o con `python -m normativa_mcp.ingest --buscar "1065/2007"`) y añadir una línea.
"""

NORMAS: dict[str, tuple[str, str]] = {
    # --- Procedimiento tributario ---
    "LGT": ("BOE-A-2003-23186", "Ley 58/2003, de 17 de diciembre, General Tributaria"),
    "RGAT": ("BOE-A-2007-15984", "RD 1065/2007, Reglamento General de gestión e inspección tributaria (RGAT)"),
    "RGR": ("BOE-A-2005-14803", "RD 939/2005, Reglamento General de Recaudación"),
    "RGRST": ("BOE-A-2004-18398", "RD 2063/2004, Reglamento general del régimen sancionador tributario"),
    "RGRVA": ("BOE-A-2005-8662", "RD 520/2005, Reglamento general de revisión en vía administrativa"),
    # --- Impuestos ---
    "LIVA": ("BOE-A-1992-28740", "Ley 37/1992, de 28 de diciembre, del Impuesto sobre el Valor Añadido"),
    "RIVA": ("BOE-A-1992-28925", "RD 1624/1992, Reglamento del Impuesto sobre el Valor Añadido"),
    "RFACT": ("BOE-A-2012-14696", "RD 1619/2012, Reglamento por el que se regulan las obligaciones de facturación"),
    "LIRPF": ("BOE-A-2006-20764", "Ley 35/2006, del Impuesto sobre la Renta de las Personas Físicas"),
    "RIRPF": ("BOE-A-2007-6820", "RD 439/2007, Reglamento del Impuesto sobre la Renta de las Personas Físicas"),
    "LIS": ("BOE-A-2014-12328", "Ley 27/2014, de 27 de noviembre, del Impuesto sobre Sociedades"),
    "RIS": ("BOE-A-2015-7771", "RD 634/2015, Reglamento del Impuesto sobre Sociedades"),
    "TRLITPAJD": ("BOE-A-1993-25359", "RDLeg 1/1993, Texto refundido de la Ley del ITP y AJD"),
    "RITPAJD": ("BOE-A-1995-15071", "RD 828/1995, Reglamento del ITP y AJD"),
    "LISD": ("BOE-A-1987-28141", "Ley 29/1987, del Impuesto sobre Sucesiones y Donaciones"),
    # --- Procedimiento administrativo y contencioso ---
    "LPAC": ("BOE-A-2015-10565", "Ley 39/2015, del Procedimiento Administrativo Común de las AAPP"),
    "LJCA": ("BOE-A-1998-16718", "Ley 29/1998, reguladora de la Jurisdicción Contencioso-administrativa"),
    # --- Contabilidad ---
    "PGC": ("BOE-A-2007-19884", "RD 1514/2007, Plan General de Contabilidad"),
}

# Sinónimos habituales que el modelo o el usuario pueden escribir.
SINONIMOS: dict[str, str] = {
    "LEY GENERAL TRIBUTARIA": "LGT",
    "58/2003": "LGT",
    "1065/2007": "RGAT",
    "REGLAMENTO DE GESTION E INSPECCION": "RGAT",
    "939/2005": "RGR",
    "2063/2004": "RGRST",
    "REGLAMENTO SANCIONADOR": "RGRST",
    "520/2005": "RGRVA",
    "REGLAMENTO DE REVISION": "RGRVA",
    "IVA": "LIVA",
    "37/1992": "LIVA",
    "1624/1992": "RIVA",
    "1619/2012": "RFACT",
    "REGLAMENTO DE FACTURACION": "RFACT",
    "IRPF": "LIRPF",
    "35/2006": "LIRPF",
    "439/2007": "RIRPF",
    "IS": "LIS",
    "27/2014": "LIS",
    "634/2015": "RIS",
    "ITP": "TRLITPAJD",
    "ITPAJD": "TRLITPAJD",
    "1/1993": "TRLITPAJD",
    "828/1995": "RITPAJD",
    "ISD": "LISD",
    "29/1987": "LISD",
    "39/2015": "LPAC",
    "29/1998": "LJCA",
    "1514/2007": "PGC",
}


def resolver_alias(texto: str) -> str | None:
    """Devuelve el alias del catálogo para un texto libre ('LGT', 'Ley 58/2003', 'BOE-A-…')."""
    if not texto:
        return None
    t = texto.strip().upper()
    if t in NORMAS:
        return t
    for alias, (boe_id, _) in NORMAS.items():
        if t == boe_id:
            return alias
    if t in SINONIMOS:
        return SINONIMOS[t]
    # Búsqueda por número oficial dentro del texto ("Ley 58/2003, General Tributaria")
    import unicodedata

    t2 = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    for clave, alias in SINONIMOS.items():
        if "/" in clave and clave in t2:
            return alias
    for clave, alias in SINONIMOS.items():
        if "/" not in clave and len(clave) > 4 and clave in t2:
            return alias
    return None
