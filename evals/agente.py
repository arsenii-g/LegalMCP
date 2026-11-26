"""Agente de prueba: conecta cualquier modelo con API compatible OpenAI (Mistral, llama-server,
LM Studio…) al MCP de normativa y ejecuta el bucle de herramientas.

    python evals/agente.py --base-url https://api.mistral.ai/v1 --model mistral-small-2603 \
        --api-key-file clave.txt --prompt-file evals/caso_inspeccion.txt --salida traza.md

Para un modelo local:  --base-url http://127.0.0.1:8080/v1 --model <nombre>  (sin clave)
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SISTEMA = """Eres un abogado fiscalista español. Antes de afirmar nada sobre normativa, usa las herramientas:
- obtener_articulo para leer cada artículo que cites (con fecha si el caso es de ejercicios pasados;
  con `apartado` si solo necesitas una parte de un artículo largo). No vuelvas a pedir lo que ya has leído.
- buscar_normativa si no sabes qué artículo aplica.
- buscar_consultas_dgt / buscar_resoluciones_teac / buscar_jurisprudencia para doctrina y sentencias, y
  obtener_documento / obtener_sentencia antes de citarlas. Si dos búsquedas no dan nada útil, dilo y sigue.
- calcular_* para plazos, prescripción, duración de procedimientos, sanciones, recargos e intereses: no calcules
  de memoria.
Solo puedes citar texto que te haya devuelto una herramienta en esta conversación. Copia la línea «CITA:».
Si una herramienta no encuentra algo, dilo; no lo completes de memoria."""


def herramientas_openai(tools) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                               "parameters": t.input_schema}} for t in tools]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key-file")
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--salida", default="traza.md")
    ap.add_argument("--temperatura", type=float, default=0.3)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--max-pasos", type=int, default=25)
    ap.add_argument("--extra", default="{}", help="JSON con parámetros extra para la API")
    ap.add_argument("--timeout", type=int, default=3600, help="segundos máximos por petición al modelo")
    a = ap.parse_args()

    clave = Path(a.api_key_file).read_text().strip() if a.api_key_file else ""
    cabeceras = {"Content-Type": "application/json", **({"Authorization": f"Bearer {clave}"} if clave else {})}
    pregunta = Path(a.prompt_file).read_text()
    traza = [f"# Traza — {a.model}\n", f"## Pregunta\n\n{pregunta}\n"]

    raiz = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(command=sys.executable, args=["-m", "normativa_mcp"], cwd=str(raiz),
                                   env={**os.environ})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as sesion:
            await sesion.initialize()
            tools = herramientas_openai((await sesion.list_tools()).tools)
            mensajes = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": pregunta}]
            t0 = time.time()
            for paso in range(1, a.max_pasos + 1):
                cuerpo = {"model": a.model, "messages": mensajes, "tools": tools, "tool_choice": "auto",
                          "temperature": a.temperatura, "max_tokens": a.max_tokens, **json.loads(a.extra)}
                for intento in range(4):
                    try:
                        resp = requests.post(f"{a.base_url}/chat/completions", headers=cabeceras, json=cuerpo,
                                             timeout=a.timeout)
                    except requests.RequestException as e:
                        resp = None
                        traza.append(f"\n**Error de conexión en el paso {paso}:** {type(e).__name__}: {e}\n")
                        print("ERROR", type(e).__name__, e)
                        break
                    if resp.status_code != 429:
                        break
                    time.sleep(5 * (intento + 1))
                if resp is None:
                    break
                if resp.status_code != 200:
                    traza.append(f"\n**Error de la API ({resp.status_code}):** {resp.text[:1000]}\n")
                    print("ERROR", resp.status_code, resp.text[:500])
                    break
                eleccion = resp.json()["choices"][0]
                msg = eleccion["message"]
                fin = eleccion.get("finish_reason")
                razonamiento = msg.get("reasoning_content") or msg.get("reasoning") or ""
                uso = resp.json().get("usage", {})
                print(f"[paso {paso}] finish_reason={fin} tokens={uso} razonamiento={len(razonamiento)} car. "
                      f"contenido={len(msg.get('content') or '')} car.", flush=True)
                if razonamiento:
                    traza.append(f"\n<details><summary>Razonamiento paso {paso} ({len(razonamiento)} car.)</summary>\n\n"
                                 f"{razonamiento}\n</details>\n")
                llamadas = msg.get("tool_calls") or []
                mensajes.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
                if not llamadas:
                    contenido = msg.get("content")
                    if isinstance(contenido, list):  # algunos modelos devuelven bloques (p. ej. pensamiento)
                        contenido = "\n".join(b.get("text", "") for b in contenido if isinstance(b, dict))
                    traza.append(f"\n## Respuesta final (paso {paso}, {time.time() - t0:.0f} s, finish_reason={fin})\n\n"
                                 f"{contenido or '(vacía)'}\n")
                    print(f"Fin en el paso {paso}")
                    break
                for ll in llamadas:
                    nombre = ll["function"]["name"]
                    try:
                        args = json.loads(ll["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"[paso {paso}] {nombre}({json.dumps(args, ensure_ascii=False)})", flush=True)
                    try:
                        res = await sesion.call_tool(nombre, args)
                        texto = "\n".join(c.text for c in res.content if hasattr(c, "text"))
                    except Exception as e:
                        texto = f"Error al ejecutar la herramienta: {e}"
                    traza.append(f"\n### Paso {paso}: `{nombre}` {json.dumps(args, ensure_ascii=False)}\n\n"
                                 f"<details><summary>resultado ({len(texto)} car.)</summary>\n\n```\n{texto[:3000]}\n```\n</details>\n")
                    mensajes.append({"role": "tool", "tool_call_id": ll["id"], "name": nombre, "content": texto})
                Path(a.salida).write_text("\n".join(traza))  # progreso guardado tras cada paso
            else:
                traza.append("\n**Se alcanzó el máximo de pasos sin respuesta final.**\n")
    Path(a.salida).write_text("\n".join(traza))
    print("Traza guardada en", a.salida)


if __name__ == "__main__":
    asyncio.run(main())
