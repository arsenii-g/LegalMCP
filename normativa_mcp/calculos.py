"""Calculadoras deterministas: plazos, prescripción, duración de procedimientos, sanciones, recargos e intereses.

Los modelos de lenguaje se equivocan con las fechas y los porcentajes; estas funciones hacen el cálculo exacto y
devuelven, además del resultado, los pasos y el fundamento legal para que el modelo pueda explicarlo y citarlo.

Limitaciones generales (se repiten en las salidas cuando aplican):
- Festivos: solo los nacionales (y los días inhábiles judiciales del art. 183 LOPJ). Los autonómicos y locales se
  pueden pasar en `festivos_adicionales`.
- Los criterios de cómputo siguen el art. 30 LPAC (plazos administrativos y tributarios), el art. 5 CC y los arts.
  46 y 128 LJCA (plazos judiciales). Los casos dudosos se señalan como advertencias.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

# --------------------------------------------------------------------------------------------------------------
# Fechas
# --------------------------------------------------------------------------------------------------------------


def fecha(s: str | date | None, por_defecto: date | None = None) -> date:
    """Acepta AAAA-MM-DD o DD/MM/AAAA."""
    if s is None or s == "":
        if por_defecto is None:
            raise ValueError("Falta una fecha")
        return por_defecto
    if isinstance(s, date):
        return s
    s = s.strip()
    if "/" in s:
        d, m, a = s.split("/")
        return date(int(a), int(m), int(d))
    return date.fromisoformat(s[:10])


def eur(x: float) -> str:
    """12.345,67 €"""
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def f(d: date) -> str:
    return d.strftime("%d/%m/%Y")


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fd(d: date) -> str:
    return f"{_DIAS[d.weekday()]} {f(d)}"


def pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l_) // 433
    mes = (h + l_ - 7 * m + 90) // 25
    dia = (h + l_ - 7 * m + 33 * mes + 19) % 32
    return date(anio, mes, dia)


def festivos_nacionales(anio: int) -> dict[date, str]:
    """Fiestas laborales de ámbito nacional comunes a todo el territorio (art. 37.2 ET y RD 2001/1983)."""
    return {
        date(anio, 1, 1): "Año Nuevo",
        date(anio, 1, 6): "Epifanía del Señor",
        pascua(anio) - timedelta(days=2): "Viernes Santo",
        date(anio, 5, 1): "Fiesta del Trabajo",
        date(anio, 8, 15): "Asunción de la Virgen",
        date(anio, 10, 12): "Fiesta Nacional de España",
        date(anio, 11, 1): "Todos los Santos",
        date(anio, 12, 6): "Día de la Constitución",
        date(anio, 12, 8): "Inmaculada Concepción",
        date(anio, 12, 25): "Natividad del Señor",
    }


@dataclass
class Calendario:
    """Días inhábiles. ámbito «administrativo» (art. 30 LPAC: sábados, domingos y festivos) o «judicial»
    (además agosto y del 24 de diciembre al 6 de enero, art. 183 LOPJ)."""

    ambito: str = "administrativo"
    adicionales: set[date] = field(default_factory=set)

    def motivo_inhabil(self, d: date) -> str | None:
        if d.weekday() == 5:
            return "sábado"
        if d.weekday() == 6:
            return "domingo"
        if d in self.adicionales:
            return "festivo indicado"
        fest = festivos_nacionales(d.year).get(d)
        if fest:
            return f"festivo nacional ({fest})"
        if self.ambito == "judicial":
            if d.month == 8:
                return "agosto (art. 183 LOPJ)"
            if (d.month == 12 and d.day >= 24) or (d.month == 1 and d.day <= 6):
                return "24 de diciembre a 6 de enero (art. 183 LOPJ)"
        return None

    def habil(self, d: date) -> bool:
        return self.motivo_inhabil(d) is None

    def siguiente_habil(self, d: date, pasos: list[str] | None = None) -> date:
        orig = d
        while not self.habil(d):
            d += timedelta(days=1)
        if pasos is not None and d != orig:
            pasos.append(f"El {fd(orig)} es inhábil ({self.motivo_inhabil(orig)}): se traslada al primer día hábil "
                         f"siguiente, {fd(d)} ({'art. 133.4 LEC y 185 LOPJ' if self.ambito == 'judicial' else 'art. 30.5 LPAC'}).")
        return d


def sumar_meses(d: date, meses: int) -> date:
    """Mismo día del mes de vencimiento; si no existe, último día del mes (art. 30.4 LPAC, art. 5 CC)."""
    total = d.month - 1 + meses
    anio, mes = d.year + total // 12, total % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def _augustos(desde_excl: date, hasta_incl: date) -> int:
    """Número de meses de agosto con algún día en (desde, hasta]."""
    n = 0
    for anio in range(desde_excl.year, hasta_incl.year + 1):
        ini, fin = date(anio, 8, 1), date(anio, 8, 31)
        if fin > desde_excl and ini <= hasta_incl:
            n += 1
    return n


def _cal(ambito: str, festivos_adicionales: list[str] | None) -> Calendario:
    return Calendario(ambito, {fecha(x) for x in (festivos_adicionales or [])})


# --------------------------------------------------------------------------------------------------------------
# Plazos
# --------------------------------------------------------------------------------------------------------------


def calcular_vencimiento(fecha_inicio: str, cantidad: int, unidad: str, ambito: str = "administrativo",
                         festivos_adicionales: list[str] | None = None) -> tuple[date, list[str]]:
    cal = _cal(ambito, festivos_adicionales)
    d0 = fecha(fecha_inicio)
    u = unidad.lower().strip()
    pasos = [f"Fecha de notificación/publicación (día inicial del que se parte): {fd(d0)}. "
             f"El cómputo empieza el día siguiente (art. 30.3-4 LPAC)."]
    if u.startswith("dias_hab") or u in ("dias", "días", "dias habiles", "días hábiles"):
        d, n = d0, 0
        while n < cantidad:
            d += timedelta(days=1)
            if cal.habil(d):
                n += 1
        pasos.append(f"Se cuentan {cantidad} días hábiles, excluidos sábados, domingos y festivos"
                     + (" y los inhábiles judiciales (agosto, 24/12-6/1)" if ambito == "judicial" else "")
                     + f" (art. 30.2 LPAC{'; art. 183 LOPJ y 128.2 LJCA' if ambito == 'judicial' else ''}).")
        pasos.append(f"Último día: {fd(d)}.")
        return d, pasos
    if u.startswith("dias_nat") or u in ("días naturales", "dias naturales"):
        d = d0 + timedelta(days=cantidad)
        pasos.append(f"{cantidad} días naturales desde el día siguiente: {fd(d)}.")
        return cal.siguiente_habil(d, pasos), pasos
    if u.startswith("mes") or u.startswith("año") or u.startswith("ano"):
        meses = cantidad * (12 if u.startswith(("año", "ano")) else 1)
        base = d0
        if ambito == "judicial" and d0.month == 8:
            base = date(d0.year, 8, 31)
            pasos.append("Notificado en agosto (inhábil, art. 128.2 LJCA): el cómputo se inicia como si se hubiera "
                         f"notificado el {f(base)}.")
        d = sumar_meses(base, meses)
        if ambito == "judicial":
            k = 0
            while _augustos(base, d) > k:
                k += 1
                d = sumar_meses(base, meses + k)
            if k:
                pasos.append(f"El plazo comprende {k} mes(es) de agosto, que no se computa (art. 128.2 LJCA): "
                             f"se alarga {k} mes(es).")
            pasos.append("Los días 24/12-6/1 no alargan un plazo por meses (ATS 23/07/2024), pero si el último "
                         "día cae en ellos se traslada al primer hábil.")
        pasos.append(f"{cantidad} {({'meses': 'mes', 'años': 'año', 'anios': 'año'}.get(u, unidad) if cantidad == 1 else unidad)} de fecha a fecha: vence el {fd(d)} (art. 30.4 LPAC; art. 5 CC).")
        return cal.siguiente_habil(d, pasos), pasos
    raise ValueError("unidad debe ser dias_habiles, dias_naturales, meses o años")


PLAZOS_RECURSO = {
    "reposicion": (1, "meses", "administrativo", "Recurso de reposición: un mes (art. 223.1 LGT)."),
    "reclamacion_economico_administrativa": (1, "meses", "administrativo",
                                             "Reclamación económico-administrativa: un mes (art. 235.1 LGT)."),
    "alzada_ordinaria": (1, "meses", "administrativo", "Recurso de alzada ordinario ante el TEAC: un mes "
                                                       "(art. 241.1 LGT)."),
    "anulacion": (15, "dias_habiles", "administrativo", "Recurso de anulación: 15 días (art. 241 bis LGT)."),
    "extraordinario_revision": (3, "meses", "administrativo", "Recurso extraordinario de revisión: tres meses desde "
                                                              "el conocimiento de los documentos o la firmeza de la "
                                                              "sentencia (art. 244.3 LGT)."),
    "contencioso_administrativo": (2, "meses", "judicial", "Recurso contencioso-administrativo: dos meses (art. 46.1 "
                                                           "LJCA); agosto no computa (art. 128.2 LJCA)."),
    "alegaciones_acta": (15, "dias_habiles", "administrativo", "Alegaciones al acta de disconformidad: 15 días "
                                                               "(art. 157.3 LGT)."),
    "alegaciones_tramite_audiencia": (10, "dias_habiles", "administrativo",
                                      "Trámite de audiencia: entre 10 y 15 días (arts. 99.8 LGT, 96.5 RGAT); se usa 10."),
    "alegaciones_propuesta_sancion": (15, "dias_habiles", "administrativo",
                                      "Alegaciones a la propuesta de sanción: 15 días (art. 210.4 LGT y 23 RGRST)."),
    "requerimiento_informacion": (10, "dias_habiles", "administrativo",
                                  "Atender un requerimiento: no inferior a 10 días (art. 93 y 141 LGT; art. 30.2 "
                                  "RGAT; compruebe el plazo concreto del requerimiento)."),
    "tasacion_pericial_contradictoria": (1, "meses", "administrativo",
                                         "Tasación pericial contradictoria: en el plazo del primer recurso o "
                                         "reclamación que proceda (art. 135.1 LGT)."),
}


def plazo_recurso(tipo: str, fecha_notificacion: str, festivos_adicionales: list[str] | None = None) -> str:
    t = tipo.lower().strip().replace(" ", "_").replace("-", "_")
    t = {"rea": "reclamacion_economico_administrativa", "tear": "reclamacion_economico_administrativa",
         "teac": "reclamacion_economico_administrativa", "contencioso": "contencioso_administrativo",
         "alzada": "alzada_ordinaria", "revision": "extraordinario_revision"}.get(t, t)
    if t not in PLAZOS_RECURSO:
        return f"Tipo no reconocido. Opciones: {', '.join(PLAZOS_RECURSO)}."
    n, u, amb, fund = PLAZOS_RECURSO[t]
    d, pasos = calcular_vencimiento(fecha_notificacion, n, u, amb, festivos_adicionales)
    return (f"## Plazo: {t.replace('_', ' ')}\n{fund}\n\n**Último día: {fd(d)}**\n\nCómputo:\n- "
            + "\n- ".join(pasos) + "\n\n" + _AVISO_FESTIVOS)


_AVISO_FESTIVOS = ("Advertencia: solo se han tenido en cuenta los festivos nacionales"
                   " (y, en vía judicial, agosto y 24/12-6/1). Compruebe los festivos autonómicos y locales del "
                   "domicilio del interesado y de la sede del órgano (art. 30.6 LPAC) y páselos en "
                   "`festivos_adicionales`. Confirme siempre el plazo indicado en el pie de recurso de la notificación.")


def plazo_pago_liquidacion(fecha_notificacion: str, festivos_adicionales: list[str] | None = None) -> str:
    """Plazo de ingreso en voluntaria de una liquidación (art. 62.2 LGT)."""
    d = fecha(fecha_notificacion)
    cal = _cal("administrativo", festivos_adicionales)
    pasos = []
    if d.day <= 15:
        v = sumar_meses(date(d.year, d.month, 20), 1)
        pasos.append(f"Notificada entre el 1 y el 15 ({f(d)}): hasta el día 20 del mes posterior, {fd(v)} "
                     "(art. 62.2.a LGT).")
    else:
        v = sumar_meses(date(d.year, d.month, 5), 2)
        pasos.append(f"Notificada entre el 16 y el último día del mes ({f(d)}): hasta el día 5 del segundo mes "
                     f"posterior, {fd(v)} (art. 62.2.b LGT).")
    v = cal.siguiente_habil(v, pasos)
    return (f"## Plazo de ingreso en periodo voluntario\n**Último día: {fd(v)}**\n\n- " + "\n- ".join(pasos)
            + "\n\nEl mismo plazo rige para la reducción del 40 % por pronto pago de sanciones (art. 188.3 LGT) y del "
              "25 % de los recargos del art. 27.5 LGT.\n\n" + _AVISO_FESTIVOS)


# --------------------------------------------------------------------------------------------------------------
# Fin del plazo de declaración (inicio de la prescripción, art. 67.1 LGT)
# --------------------------------------------------------------------------------------------------------------

# Vencimiento del plazo de presentación del IRPF por ejercicio (cuadro oficial de la AEAT, Manual Renta 2025).
VENCIMIENTO_IRPF = {
    2003: "2004-07-01", 2004: "2005-06-30", 2005: "2006-06-30", 2006: "2007-07-02", 2007: "2008-06-30",
    2008: "2009-06-30", 2009: "2010-06-30", 2010: "2011-06-30", 2011: "2012-07-02", 2012: "2013-07-01",
    2013: "2014-06-30", 2014: "2015-06-30", 2015: "2016-06-30", 2016: "2017-06-30", 2017: "2018-07-02",
    2018: "2019-07-01", 2019: "2020-06-30", 2020: "2021-06-30", 2021: "2022-06-30", 2022: "2023-06-30",
    2023: "2024-07-01", 2024: "2025-06-30", 2025: "2026-06-30",
}

_TRIM = {1: (4, 20), 2: (7, 20), 3: (10, 20)}


def fin_plazo_declaracion(tipo: str, ejercicio: int | None = None, periodo: str | None = None,
                          fecha_devengo: str | None = None, festivos_adicionales: list[str] | None = None
                          ) -> tuple[date, list[str]]:
    """Último día del plazo reglamentario de declaración para los casos más comunes."""
    cal = _cal("administrativo", festivos_adicionales)
    t = tipo.lower().strip()
    pasos: list[str] = []
    if t in ("iva_trimestral", "retenciones_trimestral", "pagos_fraccionados_irpf"):
        q = int(str(periodo).upper().replace("T", "").strip())
        if q in _TRIM:
            m, dd = _TRIM[q]
            d = date(int(ejercicio), m, dd)
            pasos.append(f"{q}T {ejercicio}: veinte primeros días naturales del mes siguiente al trimestre "
                         f"({'art. 71.4 RIVA' if t == 'iva_trimestral' else 'arts. 108 y 110 RIRPF'}): {f(d)}.")
        else:
            if t == "iva_trimestral":
                d = date(int(ejercicio) + 1, 1, 30)
                pasos.append(f"4T {ejercicio}: treinta primeros días naturales de enero (art. 71.4 RIVA): {f(d)}.")
            else:
                d = date(int(ejercicio) + 1, 1, 20)
                pasos.append(f"4T {ejercicio}: veinte primeros días naturales de enero (arts. 108 y 110 RIRPF): "
                             f"{f(d)}.")
    elif t == "iva_mensual":
        mes = int(periodo)
        siguiente = sumar_meses(date(int(ejercicio), mes, 1), 1)
        if mes == 1:
            d = date(siguiente.year, 2, calendar.monthrange(siguiente.year, 2)[1])
            pasos.append(f"Enero {ejercicio}: hasta el último día de febrero (art. 71.4 RIVA): {f(d)}.")
        elif date(int(ejercicio), mes, 1) >= date(2017, 7, 1):
            d = date(siguiente.year, siguiente.month, 30 if siguiente.month != 2 else
                     calendar.monthrange(siguiente.year, 2)[1])
            pasos.append(f"Mes {mes}/{ejercicio}: treinta primeros días naturales del mes siguiente (art. 71.4 RIVA, "
                         f"desde 1/7/2017): {f(d)}.")
        else:
            d = date(siguiente.year, siguiente.month, 20)
            pasos.append(f"Mes {mes}/{ejercicio}: veinte primeros días naturales del mes siguiente (redacción anterior "
                         f"a 1/7/2017 del art. 71.4 RIVA): {f(d)}.")
    elif t in ("irpf", "patrimonio"):
        ej = int(ejercicio)
        if ej in VENCIMIENTO_IRPF:
            d = fecha(VENCIMIENTO_IRPF[ej])
            pasos.append(f"IRPF/IP {ej}: el plazo venció el {f(d)} (cuadro oficial de vencimientos de la AEAT).")
        else:
            d = date(ej + 1, 6, 30)
            pasos.append(f"IRPF/IP {ej}: 30 de junio de {ej + 1} (fecha habitual; compruebe la orden anual del "
                         f"modelo 100).")
    elif t in ("is", "sociedades"):
        cierre = fecha(fecha_devengo) if fecha_devengo else date(int(ejercicio), 12, 31)
        seis = sumar_meses(cierre, 6)
        d = seis + timedelta(days=25)
        pasos.append(f"IS con periodo impositivo cerrado el {f(cierre)}: 25 días naturales siguientes a los 6 meses "
                     f"posteriores ({f(seis)}) (art. 124.1 LIS): {f(d)}.")
    elif t in ("isd_mortis_causa", "sucesiones"):
        dev = fecha(fecha_devengo)
        d = sumar_meses(dev, 6)
        pasos.append(f"ISD mortis causa, fallecimiento el {f(dev)}: seis meses (art. 67.1.a RISD): {f(d)}. "
                     "Las CCAA pueden regular otro plazo; existe prórroga de otros seis meses si se pide a tiempo.")
    elif t in ("isd_inter_vivos", "donaciones", "itp", "itpajd", "ajd"):
        dev = fecha(fecha_devengo)
        d, p = calcular_vencimiento(dev.isoformat(), 30, "dias_habiles", "administrativo", festivos_adicionales)
        pasos.append(f"{t.upper()}: treinta días hábiles desde el devengo {f(dev)} (art. 67.1.b RISD / art. 102 "
                     f"RITPAJD): {f(d)}. Compruebe la normativa autonómica, que puede fijar otro plazo.")
    else:
        raise ValueError("tipo no reconocido: iva_trimestral, iva_mensual, retenciones_trimestral, irpf, patrimonio, "
                         "is, isd_mortis_causa, isd_inter_vivos, itp; o pase directamente fin_plazo.")
    return cal.siguiente_habil(d, pasos), pasos


# --------------------------------------------------------------------------------------------------------------
# Prescripción (arts. 66-68 LGT)
# --------------------------------------------------------------------------------------------------------------


def prescripcion(fin_plazo: str | None = None, tipo: str | None = None, ejercicio: int | None = None,
                 periodo: str | None = None, fecha_devengo: str | None = None,
                 interrupciones: list[str] | None = None, fecha_referencia: str | None = None,
                 anios: int = 4, festivos_adicionales: list[str] | None = None) -> str:
    hoy = fecha(fecha_referencia, date.today())
    pasos: list[str] = []
    if fin_plazo:
        fin = fecha(fin_plazo)
        pasos.append(f"Fin del plazo de declaración indicado: {fd(fin)}.")
    elif tipo:
        fin, p = fin_plazo_declaracion(tipo, ejercicio, periodo, fecha_devengo, festivos_adicionales)
        pasos += p
    else:
        return "Indique `fin_plazo` o `tipo` (+ ejercicio/periodo o fecha_devengo)."
    pasos.append(f"El plazo de prescripción de {anios} años (art. 66 LGT) comienza el día siguiente, "
                 f"{fd(fin + timedelta(days=1))} (art. 67.1 LGT).")
    ultimo = sumar_meses(fin, 12 * anios)
    pasos.append(f"Cómputo de fecha a fecha: el último día para interrumpir es el {fd(ultimo)}.")
    for i in sorted(fecha(x) for x in (interrupciones or [])):
        if i <= fin:
            pasos.append(f"Actuación del {f(i)}: anterior al inicio del plazo, no interrumpe.")
        elif i > ultimo:
            pasos.append(f"Actuación del {f(i)}: posterior al {f(ultimo)}, cuando ya había prescrito; no interrumpe "
                         "(la prescripción ganada se aplica de oficio, art. 69 LGT).")
        else:
            ultimo = sumar_meses(i, 12 * anios)
            pasos.append(f"Interrupción el {f(i)} (art. 68 LGT): el plazo se reinicia; nuevo último día "
                         f"{fd(ultimo)} (art. 68.6 LGT).")
    estado = "PRESCRITO" if hoy > ultimo else "NO PRESCRITO"
    return (f"## Prescripción ({anios} años)\n**A {f(hoy)}: {estado}.** Último día para interrumpir: {fd(ultimo)}; "
            f"prescrito desde el {f(ultimo + timedelta(days=1))}.\n\n- " + "\n- ".join(pasos)
            + "\n\nNotas: (1) solo interrumpen las actuaciones que cumplan el art. 68 LGT (con conocimiento formal del "
              "obligado); si se incumplió el plazo de un procedimiento inspector, las actuaciones dentro de ese plazo "
              "no interrumpen (art. 150.6.a LGT) y no deben incluirse en `interrupciones`. (2) Según el criterio "
              "mayoritario, que el último día sea inhábil no prorroga la prescripción. (3) El derecho a comprobar "
              "bases o créditos de ejercicios prescritos tiene un plazo de 10 años (art. 66 bis LGT). (4) Delito "
              "fiscal: prescripción penal de 5 años, o 10 en los tipos agravados (arts. 131 y 305 bis CP).")


# --------------------------------------------------------------------------------------------------------------
# Duración de procedimientos
# --------------------------------------------------------------------------------------------------------------

PROCEDIMIENTOS = {
    "inspeccion": (18, "Inspección: 18 meses (art. 150.1.a LGT); 27 meses si la cifra de negocios alcanza la de "
                       "auditoría obligatoria o hay grupo de consolidación (art. 150.1.b LGT). Redacción vigente "
                       "desde el 19/10/2015 (Ley 34/2015)."),
    "inspeccion_27": (27, "Inspección: 27 meses (art. 150.1.b LGT)."),
    "comprobacion_limitada": (6, "Comprobación limitada y demás procedimientos de gestión: seis meses (art. 104.1 "
                                 "LGT). Su incumplimiento produce la caducidad (art. 104.5 LGT)."),
    "verificacion_datos": (6, "Verificación de datos: seis meses (art. 104.1 LGT)."),
    "sancionador": (6, "Procedimiento sancionador: seis meses desde la notificación de inicio (art. 211.2 LGT); su "
                       "incumplimiento produce la caducidad (art. 211.4 LGT)."),
    "apremio_embargo": (0, ""),
}


def duracion_procedimiento(tipo: str, fecha_inicio: str, dias_dilacion: int = 0, dias_suspension: int = 0,
                           dias_extension: int = 0, fecha_referencia: str | None = None,
                           fecha_terminacion: str | None = None) -> str:
    t = tipo.lower().strip()
    if t not in PROCEDIMIENTOS or not PROCEDIMIENTOS[t][0]:
        return f"Tipo no reconocido. Opciones: {', '.join(k for k, v in PROCEDIMIENTOS.items() if v[0])}."
    meses, fund = PROCEDIMIENTOS[t]
    ini = fecha(fecha_inicio)
    base = sumar_meses(ini, meses)
    extra = dias_dilacion + dias_suspension + dias_extension
    venc = base + timedelta(days=extra)
    pasos = [f"Inicio (notificación): {fd(ini)}. {meses} meses de fecha a fecha: {fd(base)}."]
    if extra:
        pasos.append(f"Se suman {extra} días (dilaciones no imputables a la Administración {dias_dilacion}, "
                     f"suspensión {dias_suspension}, extensión {dias_extension}; arts. 104.2 y 150.3-5 LGT): "
                     f"{fd(venc)}.")
    ref = fecha(fecha_terminacion) if fecha_terminacion else fecha(fecha_referencia, date.today())
    sal = [f"## Duración máxima: {t.replace('_', ' ')}", fund, f"**Vencimiento: {fd(venc)}.**", ""]
    sal += ["- " + p for p in pasos]
    if ref > venc:
        sal.append(f"\n**Plazo superado** a {f(ref)} ({(ref - venc).days} días después del vencimiento).")
        if t.startswith("inspeccion"):
            sal.append("Efectos (art. 150.6 LGT): no hay caducidad, el procedimiento continúa; a) las actuaciones "
                       "realizadas dentro del plazo no interrumpen la prescripción (solo las posteriores al "
                       f"{f(venc)}); b) los ingresos realizados desde el inicio hasta la primera actuación posterior "
                       "al incumplimiento se consideran espontáneos (art. 27 LGT); c) no se exigen intereses de demora "
                       f"desde el {f(venc + timedelta(days=1))} hasta la terminación. Para la prescripción, use la "
                       "herramienta de prescripción sin incluir las actuaciones del plazo como interrupciones.")
        else:
            sal.append("Efecto: caducidad del procedimiento (arts. 104.5 y 211.4 LGT). Las actuaciones realizadas en "
                       "un procedimiento caducado no interrumpen la prescripción (art. 104.5 LGT); el de "
                       "sancionador caducado no puede volver a iniciarse (art. 211.4 LGT).")
    else:
        sal.append(f"\nA {f(ref)} el plazo no ha vencido (quedan {(venc - ref).days} días).")
    sal.append("\nAdvertencia: compruebe las dilaciones y suspensiones reales en el expediente; el cómputo exacto de "
               "días puede discutirse.")
    return "\n".join(sal)


# --------------------------------------------------------------------------------------------------------------
# Intereses de demora (art. 26 LGT) e interés legal
# --------------------------------------------------------------------------------------------------------------

# (desde, tipo %, fuente). Cuadro oficial de la AEAT (Manual Renta 2025) y leyes de presupuestos.
TIPOS_DEMORA: list[tuple[date, float, str]] = [
    (date(1994, 1, 1), 11.0, "LPGE 1994"), (date(1997, 1, 1), 9.5, "LPGE 1997"),
    (date(1998, 1, 1), 7.5, "LPGE 1998"), (date(1999, 1, 1), 5.5, "LPGE 1999"), (date(2001, 1, 1), 6.5, "LPGE 2001"),
    (date(2002, 1, 1), 5.5, "LPGE 2002"), (date(2004, 1, 1), 4.75, "LPGE 2004"), (date(2005, 1, 1), 5.0, "LPGE 2005"),
    (date(2007, 1, 1), 6.25, "LPGE 2007"), (date(2008, 1, 1), 7.0, "LPGE 2008"),
    (date(2009, 4, 1), 5.0, "Ley 2/2008, modificada desde el 1/4/2009"),
    (date(2015, 1, 1), 4.375, "Ley 36/2014 (LPGE 2015)"), (date(2016, 1, 1), 3.75, "Ley 48/2015 y siguientes"),
    (date(2023, 1, 1), 4.0625, "Ley 31/2022 (LPGE 2023), prorrogada"),
]
TIPOS_LEGAL: list[tuple[date, float, str]] = [
    (date(2010, 1, 1), 4.0, "LPGE 2010-2014"), (date(2015, 1, 1), 3.5, "Ley 36/2014"),
    (date(2016, 1, 1), 3.0, "Ley 48/2015 y siguientes"), (date(2023, 1, 1), 3.25, "Ley 31/2022, prorrogada"),
]
ULTIMO_TIPO_CONOCIDO = date(2026, 12, 31)


def _tipo(tabla, d: date) -> tuple[float, str]:
    actual = None
    for desde, t, fuente in tabla:
        if d >= desde:
            actual = (t, fuente)
    if actual is None:
        raise ValueError(f"No hay tipo para {f(d)} (la tabla empieza en {f(tabla[0][0])}).")
    return actual


def intereses_demora(importe: float, desde: str, hasta: str, excluir: list[list[str]] | None = None,
                     tipo_interes: str = "demora") -> str:
    """Intereses de `desde` (excluido: día de vencimiento) a `hasta` (incluido), por tramos de tipo y de año,
    base 365/366, interés simple, redondeo por tramo."""
    d0, d1 = fecha(desde), fecha(hasta)
    if d1 <= d0:
        return "La fecha final debe ser posterior a la inicial."
    tabla = TIPOS_LEGAL if tipo_interes == "legal" else TIPOS_DEMORA
    excl = [(fecha(a), fecha(b)) for a, b in (excluir or [])]
    tramos: list[list] = []  # [ini, fin, tipo, fuente, dias_año]
    d = d0 + timedelta(days=1)
    while d <= d1:
        if any(a <= d <= b for a, b in excl):
            d += timedelta(days=1)
            continue
        t, fuente = _tipo(tabla, d)
        dias_anio = 366 if calendar.isleap(d.year) else 365
        if tramos and tramos[-1][2] == t and tramos[-1][4] == dias_anio and tramos[-1][1] + timedelta(days=1) == d \
                and tramos[-1][1].year == d.year:
            tramos[-1][1] = d
        else:
            tramos.append([d, d, t, fuente, dias_anio])
        d += timedelta(days=1)
    filas, total = [], 0.0
    for ini, fin, t, fuente, da in tramos:
        dias = (fin - ini).days + 1
        imp = round(importe * t / 100 * dias / da, 2)
        total += imp
        filas.append(f"| {f(ini)} – {f(fin)} | {dias} | {str(t).replace('.', ',')} % | {da} | {eur(imp)} | {fuente} |")
    avisos = []
    if d1 > ULTIMO_TIPO_CONOCIDO:
        avisos.append(f"Desde el {f(ULTIMO_TIPO_CONOCIDO + timedelta(days=1))} se aplica el último tipo conocido; "
                      "compruebe si una nueva Ley de Presupuestos lo ha cambiado.")
    if excl:
        avisos.append("Periodos excluidos: " + "; ".join(f"{f(a)}–{f(b)}" for a, b in excl) + ".")
    return ("\n".join([f"## Intereses ({'interés legal del dinero' if tipo_interes == 'legal' else 'interés de demora, art. 26 LGT'})",
                       f"Principal: {eur(importe)}. Desde el {f(d0 + timedelta(days=1))} (día siguiente al "
                       f"vencimiento, art. 26.2 LGT) hasta el {f(d1)}.",
                       f"**Total intereses: {eur(round(total, 2))}**", "",
                       "| Tramo | Días | Tipo | Base | Intereses | Fuente |", "|---|---|---|---|---|---|", *filas, "",
                       "Criterio: interés simple sobre el principal, cada tramo sobre los días de su año (365/366) y "
                       "redondeado al céntimo, como la calculadora de la AEAT. El interés de demora tributario es el "
                       "legal + 25 % salvo que la LPGE fije otro (art. 26.6 LGT). Supuestos en que no se devengan: "
                       "art. 26.4 LGT (retrasos de la Administración al resolver) y art. 150.6.c LGT (inspección "
                       "fuera de plazo); páselos en `excluir`.", *avisos]))


# --------------------------------------------------------------------------------------------------------------
# Recargos (arts. 27 y 28 LGT)
# --------------------------------------------------------------------------------------------------------------

REFORMA_11_2021 = date(2021, 7, 11)


def _meses_completos(desde: date, hasta: date) -> int:
    k = 0
    while sumar_meses(desde, k + 1) <= hasta:
        k += 1
    return k


def recargo_extemporaneo(importe: float, fin_plazo: str, fecha_presentacion: str, reduccion_25: bool = True) -> str:
    fin, pres = fecha(fin_plazo), fecha(fecha_presentacion)
    if pres <= fin:
        return "La presentación está dentro de plazo: no hay recargo."
    m = _meses_completos(fin, pres)
    doce = sumar_meses(fin, 12)
    sal = [f"## Recargo por presentación extemporánea sin requerimiento previo (art. 27 LGT)",
           f"Importe a ingresar: {eur(importe)}. Fin de plazo: {f(fin)}. Presentación: {f(pres)}. "
           f"Retraso: {(pres - fin).days} días ({m} meses completos)."]

    def bloque(pct: float, fund: str, intereses: bool) -> list[str]:
        r = round(importe * pct / 100, 2)
        out = [f"- Recargo: {pct:g} % = {eur(r)} ({fund})."]
        if reduccion_25:
            out.append(f"- Con la reducción del 25 % (art. 27.5 LGT, si se ingresa todo a tiempo): "
                       f"{eur(round(r * 0.75, 2))}.")
        if intereses:
            out.append(f"- Además, intereses de demora desde el {f(doce + timedelta(days=1))} hasta la "
                       f"presentación ({f(pres)}); use la herramienta de intereses con desde={doce.isoformat()}.")
        return out

    if pres > doce:
        nuevo = bloque(15, "más de 12 meses, art. 27.2 LGT, redacción de la Ley 11/2021", True)
        viejo = bloque(20, "más de 12 meses, redacción anterior a la Ley 11/2021", True)
    else:
        nuevo = bloque(1 + m, f"1 % + 1 % por cada uno de los {m} meses completos, art. 27.2 LGT", False)
        if m < 3:
            vp = 5
        elif m < 6:
            vp = 10
        else:
            vp = 15
        viejo = bloque(vp, "redacción anterior: 5 / 10 / 15 % dentro de 3, 6 o 12 meses", False)
    if pres >= REFORMA_11_2021:
        sal += ["**Régimen vigente (desde el 11/07/2021):**", *nuevo]
    else:
        sal += ["**Régimen aplicable a la fecha de presentación (antes del 11/07/2021):**", *viejo,
                "**Régimen de la Ley 11/2021** (aplicable retroactivamente si es más favorable y el recargo no es "
                "firme, DT 1ª.1 Ley 11/2021):", *nuevo]
    sal.append("Si hubo requerimiento previo (art. 27.1 LGT) no procede el recargo sino, en su caso, sanción. Para que "
               "se aplique, la autoliquidación debe identificar el periodo (art. 27.4 LGT).")
    return "\n".join(sal)


def recargo_periodo_ejecutivo(importe: float, situacion: str) -> str:
    s = situacion.lower()
    if s.startswith("ejecutivo") or "antes" in s:
        pct, fund = 5, "recargo ejecutivo: pago total antes de la notificación de la providencia de apremio (art. 28.2 LGT); sin intereses de demora"
    elif "reducido" in s or "plazo" in s:
        pct, fund = 10, "recargo de apremio reducido: pago de la deuda y del recargo en el plazo del art. 62.5 LGT (art. 28.3 LGT); sin intereses de demora"
    else:
        pct, fund = 20, "recargo de apremio ordinario (art. 28.4 LGT); compatible con intereses de demora desde el inicio del periodo ejecutivo (art. 28.5 LGT)"
    return f"## Recargo del periodo ejecutivo\n{pct} % de {eur(importe)} = **{eur(round(importe * pct / 100, 2))}**: {fund}."


# --------------------------------------------------------------------------------------------------------------
# Sanciones (arts. 187, 188 y 191-195 LGT)
# --------------------------------------------------------------------------------------------------------------

_REPETIDA = {"leve": 5, "grave": 15, "muy grave": 25, "muy_grave": 25}


def calcular_sancion(base: float, articulo: str = "191", ocultacion: bool = False, medios_fraudulentos: bool = False,
                     facturas_falsas: bool = False, porcentaje_llevanza_incorrecta: float = 0.0,
                     porcentaje_retenciones_no_ingresadas: float | None = None,
                     cuantia_total_debida: float | None = None, devolucion_indebida: bool = False,
                     comision_repetida: str | None = None, reduccion: str | None = None,
                     pronto_pago: bool = False, fecha_sancion: str | None = None) -> str:
    art = str(articulo).strip()
    fsan = fecha(fecha_sancion, date.today())
    nuevo = fsan >= REFORMA_11_2021
    pct_acuerdo, pct_pronto = (65, 40) if nuevo else (50, 25)
    sal = [f"## Sanción — art. {art} LGT", f"Base de la sanción: {eur(base)}."]
    pasos: list[str] = []

    if art in ("194", "195"):
        pct = 15.0
        calif = "grave"
        pasos.append(f"Infracción grave, multa proporcional del 15 % (art. {art} LGT). En el art. 195, si se trata de "
                     "partidas a deducir en la cuota o créditos, es del 50 %: compruebe el supuesto.")
    elif art in ("191", "192", "193"):
        if medios_fraudulentos:
            calif = "muy grave"
            pasos.append("Medios fraudulentos: muy grave en todo caso (art. 191.3 último párrafo y 191.4 LGT).")
        elif porcentaje_retenciones_no_ingresadas is not None and porcentaje_retenciones_no_ingresadas > 50:
            calif = "muy grave"
            pasos.append("Retenciones practicadas y no ingresadas > 50 % de la base: muy grave (art. 191.4 LGT).")
        elif (base > 3000 and ocultacion) or facturas_falsas or porcentaje_llevanza_incorrecta > 10 \
                or porcentaje_retenciones_no_ingresadas is not None:
            calif = "grave"
            motivos = []
            if base > 3000 and ocultacion:
                motivos.append("base > 3.000 € con ocultación")
            if facturas_falsas:
                motivos.append("facturas o documentos falsos o falseados")
            if porcentaje_llevanza_incorrecta > 10:
                motivos.append(f"llevanza incorrecta de libros del {porcentaje_llevanza_incorrecta:g} % (> 10 %)")
            if porcentaje_retenciones_no_ingresadas is not None:
                motivos.append("retenciones o ingresos a cuenta no ingresados (≤ 50 %)")
            pasos.append(f"Grave: {', '.join(motivos)} (art. {art}.3 LGT).")
        else:
            calif = "leve"
            pasos.append(f"Leve: base {'≤ 3.000 €' if base <= 3000 else '> 3.000 € sin ocultación'} y sin supuestos "
                         f"que la agraven (art. {art}.2 LGT).")
        pct = {"leve": 50.0, "grave": 50.0, "muy grave": 100.0}[calif]
        tope = {"leve": 50.0, "grave": 100.0, "muy grave": 150.0}[calif]
        if calif != "leve":
            if comision_repetida:
                inc = _REPETIDA[comision_repetida.lower()]
                pct += inc
                pasos.append(f"Comisión repetida (sanción firme previa {comision_repetida}): +{inc} puntos "
                             "(art. 187.1.a LGT).")
            if devolucion_indebida:
                perj = 100.0
            elif cuantia_total_debida:
                perj = base / cuantia_total_debida * 100
            else:
                perj = None
            if perj is not None:
                inc = 25 if perj > 75 else 20 if perj > 50 else 15 if perj > 25 else 10 if perj > 10 else 0
                pct += inc
                pasos.append(f"Perjuicio económico {perj:.2f} % (base / cuantía que debió ingresarse"
                             f"{'; 100 % por devolución indebida, art. 191.5' if devolucion_indebida else ''}): "
                             f"+{inc} puntos (art. 187.1.b LGT).")
            else:
                pasos.append("Perjuicio económico no calculado: indique `cuantia_total_debida` (art. 187.1.b LGT).")
            pct = min(pct, tope)
        else:
            pasos.append("La infracción leve no se gradúa: 50 % fijo.")
    else:
        return "Artículo no soportado por la calculadora: use 191, 192, 193, 194 o 195."

    sancion = round(base * pct / 100, 2)
    sal += [f"**Calificación: {calif}. Porcentaje: {pct:g} %. Sanción sin reducciones: {eur(sancion)}.**", ""]
    sal += ["- " + p for p in pasos]
    importe = sancion
    red = (reduccion or "").lower()
    if red in ("acuerdo", "acta con acuerdo"):
        importe = round(importe * (1 - pct_acuerdo / 100), 2)
        sal.append(f"- Acta con acuerdo: −{pct_acuerdo} % → {eur(importe)} (art. 188.1.a LGT). No es compatible con "
                   "la reducción por pronto pago (art. 188.3 último párrafo).")
        pronto_pago = False
    elif red == "conformidad":
        importe = round(importe * 0.70, 2)
        sal.append(f"- Conformidad: −30 % → {eur(importe)} (art. 188.1.b LGT). Se pierde si se recurre la "
                   "regularización (art. 188.2.b).")
    if pronto_pago:
        importe = round(importe * (1 - pct_pronto / 100), 2)
        sal.append(f"- Pronto pago: −{pct_pronto} % → {eur(importe)} (art. 188.3 LGT): ingreso en el plazo del art. "
                   "62.2 LGT y sin recurso contra la liquidación ni la sanción.")
    sal.append(f"\n**Importe a ingresar: {eur(importe)}.**")
    if not nuevo:
        sal.append("Régimen anterior a la Ley 11/2021 (acuerdo 50 %, pronto pago 25 %); los nuevos porcentajes pueden "
                   "aplicarse retroactivamente a sanciones no firmes (DT 1ª.2 Ley 11/2021).")
    sal.append("Advertencia: la calificación depende de hechos (ocultación según art. 184.2 LGT, medios fraudulentos "
               "art. 184.3) que debe valorar el profesional.")
    return "\n".join(sal)
