# LegalMCP — normativa tributaria española para modelos locales

Servidor [MCP](https://modelcontextprotocol.io) que da a un modelo de lenguaje (local o en la nube) acceso
verificable a la normativa tributaria española, para que cite fuentes reales en lugar de recordarlas de memoria.

- **Normativa consolidada del BOE en local** (SQLite + búsqueda de texto completo), con **todas las redacciones
  históricas** de cada artículo: se puede pedir la versión vigente en la fecha del devengo.
- **Doctrina administrativa**: consultas de la DGT (buscador PETETE) y criterios y resoluciones de los TEA (DYCTEA).
- **Jurisprudencia** del CENDOJ (Tribunal Supremo, Audiencia Nacional, TSJ), con ROJ y ECLI.
- **Calculadoras** de plazos y recursos, prescripción, duración de procedimientos, sanciones, recargos e intereses
  de demora: los modelos se equivocan con fechas y porcentajes, estas herramientas no.
- **Novedades del BOE** con contenido tributario.
- Cada respuesta incluye una línea `CITA:` con la referencia y el enlace oficial.

Lo único que sale a internet son las búsquedas de doctrina (DGT, TEA), jurisprudencia y novedades del BOE. Las
herramientas bloquean las consultas que contienen NIF, IBAN, correos o teléfonos.

## Instalación

```bash
git clone https://github.com/arsenii-g/LegalMCP.git
cd LegalMCP
python -m venv .venv
.venv/bin/pip install -e .            # Windows: .venv\Scripts\pip install -e .
.venv/bin/python -m normativa_mcp.ingest   # descarga la normativa del BOE (~1 min, ~80 MB)
```

Para leer sentencias del CENDOJ (se publican en PDF) hace falta `pdftotext`: en Debian/Ubuntu
`sudo apt install poppler-utils`; en Windows, los binarios de Poppler en el `PATH`.

Los datos se guardan en `~/.local/share/normativa-tributaria-mcp` (Linux), `%LOCALAPPDATA%\NormativaTributariaMCP`
(Windows) o en la carpeta que indique la variable `NORMATIVA_MCP_DATA`. Para actualizar la normativa basta con
volver a ejecutar `ingest` (solo descarga las normas que han cambiado).

## Uso

**stdio** (OpenCode, Claude Desktop, LM Studio, Hermes…):

```bash
.venv/bin/python -m normativa_mcp
```

Ejemplo para OpenCode en `opencode.example.json`.

**HTTP** (Open WebUI y otros clientes remotos):

```bash
.venv/bin/python -m normativa_mcp --http --port 8000     # http://127.0.0.1:8000/mcp
```

En Open WebUI: *Admin → Settings → Integrations → MCP (Streamable HTTP)*, URL `http://127.0.0.1:8000/mcp`, y en el
modelo *Function Calling = Native*.

## Herramientas

| Herramienta | Qué hace | Internet |
|---|---|---|
| `listar_normas` | Normas disponibles y fecha de actualización | no |
| `buscar_normativa` | Búsqueda por palabras en la normativa, en la redacción vigente a una fecha | no |
| `obtener_articulo` | Texto exacto de un artículo (o de un apartado) en una fecha, con su historial | no |
| `buscar_consultas_dgt` | Consultas vinculantes y generales de la DGT | sí |
| `buscar_resoluciones_teac` | Criterios del TEAC y de los TEAR | sí |
| `obtener_documento` | Texto de una consulta DGT o de una resolución TEA | sí |
| `novedades_boe` | Disposiciones tributarias publicadas en el BOE entre dos fechas | sí |
| `buscar_jurisprudencia` | Sentencias del CENDOJ por texto, órgano, jurisdicción y fechas | sí |
| `obtener_sentencia` | Texto de una sentencia por ROJ, ECLI o id, con su cita | sí |
| `calcular_plazo` | Último día de un plazo: recursos (reposición, REA, alzada, contencioso…), alegaciones, pago de liquidaciones (art. 62.2 LGT) o cualquier plazo en días o meses, con festivos nacionales, agosto y 24/12-6/1 en vía judicial | no |
| `calcular_prescripcion` | Fin del plazo de declaración (IVA, retenciones, IRPF, IS, ISD, ITP…), inicio y fin de la prescripción e interrupciones (arts. 66-68 LGT) | no |
| `calcular_duracion_procedimiento` | Vencimiento de inspección (18/27 meses), comprobación limitada, verificación y sancionador, y efectos del incumplimiento (arts. 104, 150.6, 211 LGT) | no |
| `calcular_sancion` | Calificación y cuantía de las infracciones de los arts. 191-195 LGT, con graduación (art. 187) y reducciones por conformidad, acuerdo y pronto pago (art. 188) | no |
| `calcular_recargo` | Recargos por presentación extemporánea (art. 27, régimen anterior y posterior a la Ley 11/2021) y del periodo ejecutivo (art. 28) | no |
| `calcular_intereses` | Intereses de demora (art. 26 LGT) o interés legal, por tramos con los tipos oficiales de cada año | no |

## Normas incluidas

36 normas, con todas sus redacciones históricas:

- **Procedimiento tributario:** LGT, RGAT, RGR, RGRST (sancionador), RGRVA (revisión).
- **Impuestos:** LIVA, RIVA, Reglamento de facturación, RD 1007/2023 (Verifactu), LIRPF, RIRPF, LIS, RIS, TRLIRNR,
  RIRNR, Patrimonio, Grandes Fortunas (Ley 38/2022), TRLITPAJD, RITPAJD, LISD, Impuestos Especiales y su
  reglamento, Haciendas Locales (TRLRHL), Mecenazgo (Ley 49/2002), financiación autonómica (Ley 22/2009),
  limitación de pagos en efectivo (Ley 7/2012).
- **Administrativo y contencioso:** LPAC, LRJSP, LJCA.
- **Mercantil y contable:** Ley de Sociedades de Capital, Código de Comercio, PGC, PGC PYMES, Ley de Auditoría.
- **Penal y civil:** Código Penal (delitos contra la Hacienda Pública), Código Civil.

Para añadir otra, ver `normativa_mcp/catalogo.py`.

## Pruebas

```bash
.venv/bin/python -m tests.test_calculos          # calculadoras
.venv/bin/python -m tests.test_jurisprudencia    # CENDOJ (añada LEGALMCP_LIVE=1 para la prueba en vivo)
```

## Evaluación

`evals/agente.py` conecta cualquier modelo con API compatible con OpenAI al MCP y guarda la traza completa:

```bash
.venv/bin/python evals/agente.py --base-url http://127.0.0.1:8080/v1 --model mi-modelo \
    --prompt-file evals/caso_inspeccion.txt --salida traza.md --temperatura 1.0
```

## Aviso

Herramienta de apoyo para profesionales. No sustituye el criterio de un abogado o asesor fiscal: verifique siempre
las fuentes citadas antes de usarlas.

## Licencia

MIT. Los textos normativos proceden del BOE (datos abiertos) y la doctrina de los buscadores oficiales del
Ministerio de Hacienda.
