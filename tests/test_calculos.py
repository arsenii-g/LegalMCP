"""Pruebas de las calculadoras. Ejecutar: python -m tests.test_calculos  (o pytest)."""

from datetime import date

from normativa_mcp import calculos as c


def test_festivos_y_pascua():
    assert c.pascua(2024) == date(2024, 3, 31)
    assert c.pascua(2025) == date(2025, 4, 20)
    assert date(2025, 4, 18) in c.festivos_nacionales(2025)  # Viernes Santo
    cal = c.Calendario("judicial")
    assert not cal.habil(date(2025, 8, 12)) and not cal.habil(date(2025, 12, 29))
    assert c.Calendario().habil(date(2025, 8, 12))


def test_sumar_meses_fin_de_mes():
    assert c.sumar_meses(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert c.sumar_meses(date(2024, 3, 10), 18) == date(2025, 9, 10)


def test_caso_inspeccion_duracion():
    s = c.duracion_procedimiento("inspeccion", "2024-03-10", fecha_referencia="2025-11-20")
    assert "10/09/2025" in s and "Plazo superado" in s and "150.6" in s


def test_caso_inspeccion_prescripcion_iva_2021():
    estados = {}
    for q in ("1T", "2T", "3T", "4T"):
        s = c.prescripcion(tipo="iva_trimestral", ejercicio=2021, periodo=q, fecha_referencia="2025-11-20")
        estados[q] = "NO PRESCRITO" not in s
    assert estados == {"1T": True, "2T": True, "3T": True, "4T": False}
    s = c.prescripcion(tipo="iva_trimestral", ejercicio=2021, periodo="4T", fecha_referencia="2025-11-20")
    assert "31/01/2022" in s and "31/01/2026" in s  # 30/01/2022 era domingo


def test_prescripcion_interrupcion():
    s = c.prescripcion(fin_plazo="2021-04-20", interrupciones=["2024-03-10"], fecha_referencia="2025-11-20")
    assert "NO PRESCRITO" in s and "10/03/2028" in s
    s = c.prescripcion(fin_plazo="2021-04-20", interrupciones=["2025-05-01"], fecha_referencia="2025-11-20")
    assert "PRESCRITO" in s and "no interrumpe" in s


def test_fin_plazo_otros_impuestos():
    assert c.fin_plazo_declaracion("is", 2021)[0] == date(2022, 7, 25)
    assert c.fin_plazo_declaracion("irpf", 2021)[0] == date(2022, 6, 30)
    assert c.fin_plazo_declaracion("retenciones_trimestral", 2024, "4T")[0] == date(2025, 1, 20)
    assert c.fin_plazo_declaracion("iva_mensual", 2025, "1")[0] == date(2025, 2, 28)


def test_sancion_caso_rubrica():
    s = c.calcular_sancion(12000, "191", reduccion="conformidad", pronto_pago=True, fecha_sancion="2026-01-15")
    assert "leve" in s and "6.000,00 €" in s and "4.200,00 €" in s and "2.520,00 €" in s


def test_sancion_grave_graduada():
    s = c.calcular_sancion(12000, "191", ocultacion=True, cuantia_total_debida=30000, comision_repetida="leve")
    assert "grave" in s and "70 %" in s and "8.400,00 €" in s
    s = c.calcular_sancion(100000, "191", medios_fraudulentos=True, cuantia_total_debida=100000,
                           comision_repetida="muy grave")
    assert "150 %" in s  # 100 + 25 + 25, con tope 150


def test_sancion_regimen_anterior():
    s = c.calcular_sancion(10000, "191", reduccion="conformidad", pronto_pago=True, fecha_sancion="2020-05-01")
    assert "2.625,00 €" in s  # 5.000 × 0,70 × 0,75


def test_recargos():
    s = c.recargo_extemporaneo(5000, "2025-04-21", "2025-07-25")
    assert "4 %" in s and "200,00 €" in s and "150,00 €" in s
    s = c.recargo_extemporaneo(5000, "2024-01-30", "2025-03-01")
    assert "15 %" in s and "750,00 €" in s
    assert "100,00 €" in c.recargo_periodo_ejecutivo(1000, "reducido")


def test_intereses():
    s = c.intereses_demora(10000, "2022-01-31", "2025-09-10")
    assert "1.437,24 €" in s
    s = c.intereses_demora(1000, "2015-06-30", "2016-02-01")
    assert "25,33 €" in s


def test_plazos_recurso():
    assert "28/02/2025" in c.plazo_recurso("reposicion", "2025-01-31")
    assert "15/09/2025" in c.plazo_recurso("contencioso", "2025-06-15")  # agosto no computa
    assert "12/01/2026" in c.plazo_recurso("contencioso", "2025-11-10")  # 10/01 sábado
    assert "05/01/2026" in c.plazo_pago_liquidacion("2025-11-20")


if __name__ == "__main__":
    n = 0
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            fn()
            n += 1
    print(f"{n} pruebas OK")
