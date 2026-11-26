"""Pruebas locales y consulta voluntaria al CENDOJ."""
import os
import sqlite3
import unittest

from normativa_mcp import jurisprudencia as j


def test_validacion():
    assert "BLOQUEADO" in j.buscar_jurisprudencia("correo cliente@example.com")
    assert "Fecha no válida" in j.buscar_jurisprudencia("IVA", desde="2025-02-30")
    assert "Identificador no válido" in j.obtener_sentencia(None, "https://example.com")


def test_resultados():
    h = ('<div class="title"><a href="' + j.BASE + 'AN/openDocument/a24109724672cb5f/20120403" '
         'data-roj="STS 1802/2012">STS, a 28 de febrero de 2012 - ROJ: STS 1802/2012</a></div>'
         '<div class="metadatos"><ul><li><b>ECLI:ES:TS:2012:1802</b></li></ul></div>'
         '<div class="summary">Prescripci&oacute;n</div>')
    f, = j._resultados(h)
    assert f["id"].endswith("/20120403") and f["resumen"] == "Prescripción"
    assert f["meta"] == "ECLI:ES:TS:2012:1802"
    assert j._resultados("0 resultados") == []
    with unittest.TestCase().assertRaises(ValueError):
        j._resultados("Verificación")


def test_live():
    if os.environ.get("LEGALMCP_LIVE") != "1":
        raise unittest.SkipTest("Prueba en línea desactivada")
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE cache(clave TEXT PRIMARY KEY, fuente TEXT, contenido TEXT)")
    resultado = j.buscar_jurisprudencia("interrupción prescripción actuaciones inspectoras plazo 18 meses")
    assert resultado.startswith("- id:"), resultado
    ident = resultado.splitlines()[0].removeprefix("- id: ")
    roj = resultado.split("ROJ: ", 1)[1].split(" ·")[0]
    sentencia = j.obtener_sentencia(con, roj)
    assert sentencia.startswith("CITA:") and roj in sentencia, sentencia[:300]
    assert j.obtener_sentencia(con, ident) == sentencia
    print(sentencia[:380])
    penal = j.buscar_jurisprudencia("delito contra la hacienda pública cuota defraudada 120.000", jurisdiccion="penal")
    assert "Sala de lo Penal" in penal, penal[:300]
    print(penal[:380])


if __name__ == "__main__":
    suite = unittest.TestSuite(unittest.FunctionTestCase(fn) for fn in (test_validacion, test_resultados, test_live))
    raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
