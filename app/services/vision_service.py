"""
Vision service — identifies a grocery product from a photo using Gemini.

Pure Python (httpx only, no NiceGUI dependency) so it can be exercised
in isolation. The API key never leaves the server: the browser only
uploads the photo bytes to us, and we call Gemini from here.
"""
import base64
import json
import os

import httpx

from app.services.grocery_service import CATEGORIES

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
    """Base class for photo-identification failures."""


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
) -> tuple[str, str]:
    """Return (product_name, category) or raise a VisionError subclass."""
    api_key = _get_api_key()
    if not api_key:
        raise VisionNotConfigured("GEMINI_API_KEY is not set")

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

    url = GEMINI_ENDPOINT.format(model=_get_model())
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        print(f"Gemini request failed: {e}", flush=True)
        raise VisionError("Gemini request failed") from e

    if response.status_code != 200:
        print(f"Gemini returned status {response.status_code}: {response.text[:500]}", flush=True)
        raise VisionError(f"Gemini returned status {response.status_code}")

    try:
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Unexpected Gemini response shape: {e} — body: {str(body)[:500]}", flush=True)
        raise VisionError("Unexpected Gemini response shape") from e

    name = (result.get("nombre") or "").strip()
    if not result.get("reconocido") or not name:
        raise VisionUnrecognized("No product recognized in the photo")

    category = result.get("categoria") or "Otros"
    if category not in CATEGORIES:
        category = "Otros"

    return name, category
