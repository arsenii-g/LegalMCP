# LegalMCP — normativa tributaria española para modelos locales

Servidor [MCP](https://modelcontextprotocol.io) que da a un modelo de lenguaje (local o en la nube) acceso
verificable a la normativa tributaria española, para que cite fuentes reales en lugar de recordarlas de memoria.

- **Normativa consolidada del BOE en local** (SQLite + búsqueda de texto completo), con **todas las redacciones
  históricas** de cada artículo: se puede pedir la versión vigente en la fecha del devengo.
- **Doctrina administrativa**: consultas de la DGT (buscador PETETE) y criterios y resoluciones de los TEA (DYCTEA).
- **Novedades del BOE** con contenido tributario.
- Cada respuesta incluye una línea `CITA:` con la referencia y el enlace oficial.

Lo único que sale a internet son las búsquedas de doctrina (DGT, TEAC) y las novedades del BOE. Las herramientas
bloquean las consultas que contienen NIF, IBAN, correos o teléfonos.

## Instalación

```bash
git clone https://github.com/arsenii-g/LegalMCP.git
cd LegalMCP
python -m venv .venv
.venv/bin/pip install -e .            # Windows: .venv\Scripts\pip install -e .
.venv/bin/python -m normativa_mcp.ingest   # descarga la normativa del BOE (~30 s, ~45 MB)
```

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

## Normas incluidas

LGT, RGAT, RGR, RGRST, RGRVA, LIVA, RIVA, Reglamento de facturación, LIRPF, RIRPF, LIS, RIS, TRLITPAJD, RITPAJD,
LISD, LPAC, LJCA y PGC. Para añadir otra, ver `normativa_mcp/catalogo.py`.

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
