"""Catálogo de normas que se descargan del BOE (texto consolidado).

Cada entrada: alias corto -> (identificador BOE, nombre para citar).
Los identificadores están verificados contra la API de datos abiertos del BOE.
Para añadir una norma: buscar su identificador en https://www.boe.es/buscar/legislacion.php
(o con `python -m normativa_mcp.ingest --buscar "1065/2007"`) y añadir una línea.
"""

import re
import unicodedata


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
    "TRLIRNR": ("BOE-A-2004-4527", "RDLeg 5/2004, Texto refundido de la Ley del Impuesto sobre la Renta de no Residentes"),
    "RIRNR": ("BOE-A-2004-14532", "RD 1776/2004, Reglamento del Impuesto sobre la Renta de no Residentes"),
    "LIP": ("BOE-A-1991-14392", "Ley 19/1991, del Impuesto sobre el Patrimonio"),
    "ITSGF": ("BOE-A-2022-22684", "Ley 38/2022, de gravámenes temporales y del Impuesto Temporal de Solidaridad de las Grandes Fortunas"),
    "LIIEE": ("BOE-A-1992-28741", "Ley 38/1992, de Impuestos Especiales"),
    "RIIEE": ("BOE-A-1995-18266", "RD 1165/1995, Reglamento de los Impuestos Especiales"),
    "TRLRHL": ("BOE-A-2004-4214", "RDLeg 2/2004, Texto refundido de la Ley Reguladora de las Haciendas Locales"),
    "LMECENAZGO": ("BOE-A-2002-25039", "Ley 49/2002, de régimen fiscal de las entidades sin fines lucrativos y de los incentivos fiscales al mecenazgo"),
    "LFCCAA": ("BOE-A-2009-20375", "Ley 22/2009, de financiación de las Comunidades Autónomas de régimen común"),
    "LLPE": ("BOE-A-2012-13416", "Ley 7/2012, de prevención y lucha contra el fraude"),
    "RVERIFACTU": ("BOE-A-2023-24840", "RD 1007/2023, Reglamento de requisitos de los sistemas informáticos de facturación"),
    # --- Procedimiento administrativo y contencioso ---
    "LPAC": ("BOE-A-2015-10565", "Ley 39/2015, del Procedimiento Administrativo Común de las AAPP"),
    "LJCA": ("BOE-A-1998-16718", "Ley 29/1998, reguladora de la Jurisdicción Contencioso-administrativa"),
    "LRJSP": ("BOE-A-2015-10566", "Ley 40/2015, de Régimen Jurídico del Sector Público"),
    # --- Mercantil y contabilidad ---
    "PGC": ("BOE-A-2007-19884", "RD 1514/2007, Plan General de Contabilidad"),
    "LSC": ("BOE-A-2010-10544", "RDLeg 1/2010, Texto refundido de la Ley de Sociedades de Capital"),
    "CCOM": ("BOE-A-1885-6627", "Código de Comercio (1885)"),
    "PGCPYMES": ("BOE-A-2007-19966", "RD 1515/2007, Plan General de Contabilidad de Pequeñas y Medianas Empresas"),
    "LAC": ("BOE-A-2015-8147", "Ley 22/2015, de Auditoría de Cuentas"),
    # --- Penal y civil ---
    "CP": ("BOE-A-1995-25444", "Ley Orgánica 10/1995, del Código Penal"),
    "CC": ("BOE-A-1889-4763", "Código Civil (1889)"),
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
    "5/2004": "TRLIRNR",
    "IRNR": "TRLIRNR",
    "1776/2004": "RIRNR",
    "REGLAMENTO DEL IRNR": "RIRNR",
    "19/1991": "LIP",
    "IMPUESTO SOBRE EL PATRIMONIO": "LIP",
    "38/2022": "ITSGF",
    "GRANDES FORTUNAS": "ITSGF",
    "38/1992": "LIIEE",
    "IMPUESTOS ESPECIALES": "LIIEE",
    "1165/1995": "RIIEE",
    "REGLAMENTO DE LOS IMPUESTOS ESPECIALES": "RIIEE",
    "2/2004": "TRLRHL",
    "HACIENDAS LOCALES": "TRLRHL",
    "PLUSVALIA": "TRLRHL",
    "IIVTNU": "TRLRHL",
    "IBI": "TRLRHL",
    "IAE": "TRLRHL",
    "ICIO": "TRLRHL",
    "49/2002": "LMECENAZGO",
    "MECENAZGO": "LMECENAZGO",
    "22/2009": "LFCCAA",
    "FINANCIACION AUTONOMICA": "LFCCAA",
    "7/2012": "LLPE",
    "PAGOS EN EFECTIVO": "LLPE",
    "1007/2023": "RVERIFACTU",
    "VERIFACTU": "RVERIFACTU",
    "VERI*FACTU": "RVERIFACTU",
    "40/2015": "LRJSP",
    "REGIMEN JURIDICO DEL SECTOR PUBLICO": "LRJSP",
    "1/2010": "LSC",
    "SOCIEDADES DE CAPITAL": "LSC",
    "CODIGO DE COMERCIO": "CCOM",
    "1515/2007": "PGCPYMES",
    "PGC PYMES": "PGCPYMES",
    "22/2015": "LAC",
    "AUDITORIA DE CUENTAS": "LAC",
    "10/1995": "CP",
    "CODIGO PENAL": "CP",
    "CODIGO CIVIL": "CC",
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
    t2 = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    for numero in re.findall(r"(?<!\d)\d+/\d{4}(?!\d)", t2):
        if numero in SINONIMOS:
            return SINONIMOS[numero]
    for clave in sorted(SINONIMOS, key=len, reverse=True):
        if "/" not in clave and len(clave) > 4 and clave in t2:
            return SINONIMOS[clave]
    return None
