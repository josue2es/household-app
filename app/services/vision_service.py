"""
Vision service — identifies a grocery product from a photo using Gemini.

Pure Python (httpx only, no NiceGUI dependency) so it can be exercised
in isolation. The API key never leaves the server: the browser only
uploads the photo bytes to us, and we call Gemini from here.
"""
import base64
import json
import logging
import os
import time

import httpx

from app.services.grocery_service import CATEGORIES

# One log line per identification attempt (success or failure), tagged with
# the attempt's reference code, so a problem reported from the UI can be
# found in `journalctl` / `docker compose logs` by grepping for that code.
log = logging.getLogger("household.vision")

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# The model can process a photo in a few seconds under normal load, but
# `pro` variants occasionally take longer — give it generous headroom.
REQUEST_TIMEOUT = 60.0

# Keep the catalog list in the prompt bounded; it's already sorted by
# purchase frequency, so the most relevant names come first.
MAX_CATALOG_NAMES_IN_PROMPT = 300

PROMPT_TEMPLATE = """\
Eres un asistente que identifica productos de supermercado para la lista de compras de un
hogar hispanohablante. Observa la foto e identifica el producto principal (el más prominente).

Reglas:
- Devuelve el nombre en español, corto y genérico (ej. "Leche", "Arroz", "Papel higiénico"),
  sin marca, salvo que la marca sea imprescindible para identificar el producto.
- Si el producto corresponde a uno de los nombres ya existentes en el catálogo del usuario
  (lista abajo), devuelve EXACTAMENTE ese nombre del catálogo.
- Elige la categoría según esta guía:
  Despensa (arroz, frijoles, café, aceite, enlatados), Frescos (frutas y verduras),
  Carnes y Lácteos (huevos, queso, leche, pollo, carne), Panadería (tortillas, pan),
  Cuidado Personal (papel higiénico, shampoo, pasta dental), Limpieza del Hogar (detergente,
  jabón de trastes, escobas), Mascotas (comida y artículos para mascotas), Otros (pilas,
  cerillos, focos y todo lo demás).
- Si la imagen no muestra un producto de supermercado identificable, devuelve
  reconocido=false.

Nombres existentes en el catálogo:
{catalog_names}
"""


class VisionError(Exception):
    """
    Base class for photo-identification failures.

    `str(error)` is a short message in Spanish for the user; `detail` is the
    technical reason (HTTP status, Gemini's own message, finish reason, ...)
    for the logs and for the small print under the message.
    """

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class VisionNotConfigured(VisionError):
    """GEMINI_API_KEY is not set."""


class VisionUnrecognized(VisionError):
    """The model could not identify a grocery product in the photo."""


def _get_api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or ""


def _get_model() -> str:
    return os.getenv("GEMINI_MODEL") or "gemini-3-pro-preview"


async def identify_grocery_from_photo(
    image_bytes: bytes,
    mime_type: str,
    catalog_names: list[str],
    ref: str = "-",
) -> tuple[str, str]:
    """
    Return (product_name, category) or raise a VisionError subclass.

    `ref` is a short code identifying this attempt in the logs.
    """
    model = _get_model()
    about = f"model {model}, image {len(image_bytes) / 1024:.0f} KB {mime_type}"
    started = time.monotonic()
    try:
        name, category = await _identify(image_bytes, mime_type, catalog_names, model)
    except VisionUnrecognized as e:
        log.warning("[%s] No product recognized after %.1f s (%s): %s",
                    ref, time.monotonic() - started, about, e.detail)
        raise
    except VisionError as e:
        log.error("[%s] Photo identification failed after %.1f s (%s): %s | %s",
                  ref, time.monotonic() - started, about, e, e.detail)
        raise
    log.info("[%s] Identified %r (%s) in %.1f s (%s)",
             ref, name, category, time.monotonic() - started, about)
    return name, category


async def _identify(
    image_bytes: bytes,
    mime_type: str,
    catalog_names: list[str],
    model: str,
) -> tuple[str, str]:
    api_key = _get_api_key()
    if not api_key:
        raise VisionNotConfigured("Falta configurar GEMINI_API_KEY en el servidor",
                                  "GEMINI_API_KEY is not set")

    prompt = PROMPT_TEMPLATE.format(
        catalog_names=", ".join(catalog_names[:MAX_CATALOG_NAMES_IN_PROMPT])
    )

    payload = {
        "contents": [{
            "parts": [
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    }
                },
                {"text": prompt},
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "reconocido": {"type": "BOOLEAN"},
                    "nombre": {"type": "STRING"},
                    "categoria": {"type": "STRING", "enum": CATEGORIES},
                },
                "required": ["reconocido", "nombre", "categoria"],
            },
        },
    }

    url = GEMINI_ENDPOINT.format(model=model)
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        raise VisionError("Gemini no respondió a tiempo",
                          f"no response within {REQUEST_TIMEOUT:.0f} s ({type(e).__name__})") from e
    except httpx.HTTPError as e:
        raise VisionError("No se pudo conectar con Gemini", f"{type(e).__name__}: {e}") from e

    if response.status_code != 200:
        raise _http_error(response, model)

    try:
        body = response.json()
    except ValueError as e:
        raise VisionError(
            "Gemini devolvió una respuesta inválida",
            f"HTTP 200 but not JSON (Content-Type {response.headers.get('content-type')}): "
            f"{response.text[:300]!r}",
        ) from e

    result = _parse_result(body)

    name = str(result.get("nombre") or "").strip()
    if not result.get("reconocido") or not name:
        raise VisionUnrecognized("No se reconoció ningún producto en la foto",
                                 f"model answered {json.dumps(result, ensure_ascii=False)}")

    category = result.get("categoria") or "Otros"
    if category not in CATEGORIES:
        category = "Otros"

    return name, category


def _http_error(response: httpx.Response, model: str) -> VisionError:
    """Turn a non-200 Gemini response into a VisionError with its real reason."""
    status = response.status_code
    try:
        error = response.json()["error"]
        reason = f"HTTP {status} {error.get('status', '')}: {error.get('message', '')}"
        message = error.get("message", "")
    except (ValueError, KeyError, TypeError):
        reason = f"HTTP {status}: {response.text[:300]!r}"
        message = ""

    if status in (401, 403) or "API key" in message:
        text = "La clave GEMINI_API_KEY no es válida o no tiene permiso"
    elif status == 404:
        text = f"El modelo '{model}' no existe o ya no está disponible (revisa GEMINI_MODEL)"
    elif status == 429:
        text = "Se agotó la cuota de Gemini (demasiadas solicitudes)"
    elif status >= 500:
        text = "Gemini tuvo un error interno; intenta de nuevo en un momento"
    else:
        text = "Gemini rechazó la solicitud"
    return VisionError(text, reason)


def _parse_result(body: dict) -> dict:
    """Extract the JSON answer from a generateContent response body."""
    if not isinstance(body, dict):
        raise VisionError("Gemini devolvió una respuesta inválida",
                          f"expected a JSON object, got {json.dumps(body)[:300]}")
    block_reason = (body.get("promptFeedback") or {}).get("blockReason")
    if block_reason:
        raise VisionError("Gemini bloqueó la foto", f"promptFeedback.blockReason={block_reason}")

    candidates = body.get("candidates") or []
    if not candidates:
        raise VisionError("Gemini devolvió una respuesta vacía",
                          f"no candidates: {json.dumps(body)[:300]}")

    candidate = candidates[0]
    finish = candidate.get("finishReason", "?")
    # The answer can come in several parts; skip "thought" parts (the model's
    # reasoning) and join the text of the rest.
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))

    if not text:
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"):
            raise VisionError("Gemini bloqueó la foto", f"finishReason={finish}")
        raise VisionError("Gemini devolvió una respuesta vacía", f"finishReason={finish}, no text")

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        if finish == "MAX_TOKENS":
            raise VisionError("La respuesta de Gemini quedó incompleta",
                              f"finishReason=MAX_TOKENS, text={text[:300]!r}") from e
        raise VisionError("Gemini devolvió una respuesta inválida",
                          f"finishReason={finish}, not JSON: {text[:300]!r}") from e
    if not isinstance(result, dict):
        raise VisionError("Gemini devolvió una respuesta inválida",
                          f"expected a JSON object, got {text[:300]!r}")
    return result
