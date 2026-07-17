# Instrucciones: Identificar artículo de la lista de compras por foto (Gemini)

> **Para el implementador (IA o humano):** Este documento es la especificación completa de la
> funcionalidad. Las decisiones de diseño ya fueron tomadas con el dueño del proyecto — no las
> re-decidas. Implementa exactamente lo descrito; donde el documento diga "referencia", el código
> mostrado es una guía que debes validar contra la versión real de las librerías instaladas.

---

## 1. Objetivo

En la página **Lista de compras** (`/groceries`), agregar una opción para identificar un artículo
tomando una foto con el teléfono:

1. El usuario toca un botón "Identificar con foto".
2. Se abre directamente la **cámara trasera** del teléfono (sin selector de galería).
3. El usuario toma la foto; ésta se sube al servidor.
4. El servidor envía la foto a la **API de Gemini** (modelo `gemini-3-pro-preview`) que devuelve
   el **nombre del producto** (en español) y su **categoría** (una de las 8 categorías fijas).
5. La app muestra un **diálogo de confirmación** con nombre y categoría editables.
6. Al confirmar, el artículo se agrega a la lista activa usando la lógica existente
   (`add_to_active_list`), exactamente igual que si se hubiera escrito a mano.

## 2. Decisiones de diseño ya tomadas (no cambiar)

| Decisión | Valor elegido |
|---|---|
| Confirmación antes de agregar | **Sí** — diálogo con nombre y categoría editables |
| Origen de la foto | **Solo cámara directa** (`capture="environment"`), sin galería |
| Productos por foto | **Uno** — el producto principal/más prominente |
| Modelo de IA | `gemini-3-pro-preview`, configurable vía env var `GEMINI_MODEL` |
| API key | El dueño ya tiene una; se configura vía env var `GEMINI_API_KEY` |
| Persistencia de fotos | **Ninguna** — la foto se procesa en memoria y se descarta |
| Dependencias nuevas | Solo `httpx` (ya es dependencia transitiva de NiceGUI). **No** agregar SDK de Google ni Pillow |

## 3. Contexto de la app (lo que necesitas saber)

- **Stack:** Python 3.12, NiceGUI 2.7.0 (renderiza Quasar/Vue), SQLAlchemy 2.0, SQLite,
  Docker Compose. App móvil-first usada desde el navegador del teléfono.
- **Restricción importante:** la app se sirve por **HTTP plano** (no HTTPS), por lo que
  `getUserMedia` (cámara en vivo dentro de la página) **no funciona**. La única vía confiable es
  un `<input type="file" accept="image/*" capture="environment">`, que abre la app de cámara
  nativa y funciona sobre HTTP. En NiceGUI esto se logra con `ui.upload`.
- **Archivos relevantes:**
  - `app/pages/groceries_page.py` — página de compras. Contiene `_render_smart_add()` (input +
    botón "Agregar a la lista"), `_do_add()` (persiste y refresca) y `_show_category_dialog()`
    (diálogo de categoría para artículos nuevos). Aquí vive la lista `CATEGORIES`.
  - `app/services/grocery_service.py` — lógica de negocio. `add_to_active_list()` ya maneja:
    búsqueda case-insensitive en el catálogo, creación de artículos nuevos, y deduplicación en la
    lista activa. **Si el artículo ya existe en el catálogo, el parámetro `category` se ignora**
    (se conserva la categoría almacenada).
  - `app/ui_helpers.py` — `show_success()` / `show_error()` (notificaciones).
  - `app/main.py` — rutas; lee env vars con `os.environ.get`.
  - `.env.example`, `docker-compose.yml` — patrón existente para pasar env vars al contenedor.
- **Convenciones del repo:** código y comentarios en inglés; textos de UI en español; docstrings
  de módulo explicando responsabilidades; servicios reciben la sesión `db` como argumento.

## 4. Cambios requeridos, archivo por archivo

### 4.1 `app/services/grocery_service.py` — mover `CATEGORIES`

Mover la lista `CATEGORIES` desde `groceries_page.py` a `grocery_service.py` (fuente única de
verdad), y en `groceries_page.py` importarla desde ahí. El nuevo servicio de visión también la
importará. No cambiar su contenido ni orden:

```python
CATEGORIES = [
    "Despensa",
    "Frescos",
    "Carnes y Lácteos",
    "Panadería",
    "Cuidado Personal",
    "Limpieza del Hogar",
    "Mascotas",
    "Otros",
]
```

### 4.2 Nuevo archivo: `app/services/vision_service.py`

Servicio que encapsula la llamada a Gemini. Sin dependencia de NiceGUI (puro Python + httpx),
para poder probarlo aislado.

**Interfaz:**

```python
async def identify_grocery_from_photo(
    image_bytes: bytes,
    mime_type: str,
    catalog_names: list[str],
) -> tuple[str, str]:
    """Return (product_name, category) or raise a VisionError subclass."""
```

**Excepciones propias** (para que la UI muestre mensajes distintos):

```python
class VisionError(Exception):
    """Base class for photo-identification failures."""

class VisionNotConfigured(VisionError):
    """GEMINI_API_KEY is not set."""

class VisionUnrecognized(VisionError):
    """The model could not identify a grocery product in the photo."""
```

**Comportamiento:**

1. Leer `GEMINI_API_KEY` de `os.getenv`. Si está vacía → `VisionNotConfigured`.
2. Leer el modelo de `os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")`.
3. Hacer POST con `httpx.AsyncClient` (timeout **60 s**; el modelo pro puede tardar varios
   segundos) a:

   ```
   https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent
   ```

   Headers: `x-goog-api-key: <API key>` y `Content-Type: application/json`.

4. Cuerpo de la petición (referencia — usar salida estructurada JSON):

   ```json
   {
     "contents": [{
       "parts": [
         {"inlineData": {"mimeType": "<mime de la foto>", "data": "<foto en base64>"}},
         {"text": "<prompt, ver abajo>"}
       ]
     }],
     "generationConfig": {
       "responseMimeType": "application/json",
       "responseSchema": {
         "type": "OBJECT",
         "properties": {
           "reconocido": {"type": "BOOLEAN"},
           "nombre": {"type": "STRING"},
           "categoria": {"type": "STRING", "enum": ["Despensa", "Frescos", "Carnes y Lácteos", "Panadería", "Cuidado Personal", "Limpieza del Hogar", "Mascotas", "Otros"]}
         },
         "required": ["reconocido", "nombre", "categoria"]
       }
     }
   }
   ```

   ⚠️ **No** configurar `temperature` (Google recomienda dejar el default en Gemini 3) y **no**
   configurar `thinkingConfig` — mantener la petición mínima. Construir el `enum` de categorías a
   partir de `CATEGORIES` importado, no copiado a mano.

5. **Prompt** (texto exacto de partida; puedes ajustar redacción menor si mejora resultados, pero
   conserva todos los requisitos):

   ```
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
   {nombres separados por coma}
   ```

   Limitar los nombres del catálogo incluidos en el prompt a los primeros **300** (ya vienen
   ordenados por frecuencia de compra desde `search_suggestions`).

6. **Parseo de la respuesta:** el JSON está en
   `respuesta["candidates"][0]["content"]["parts"][0]["text"]` como string → `json.loads`.
   - Si `reconocido` es `false` o `nombre` viene vacío → `VisionUnrecognized`.
   - Si `categoria` no está en `CATEGORIES` (defensa extra) → usar `"Otros"`.
   - Devolver `(nombre.strip(), categoria)`.
7. **Errores HTTP:** ante status ≠ 200, timeout, o estructura inesperada → lanzar `VisionError`
   con un mensaje que incluya el status code (para el log), no el cuerpo completo. Hacer
   `print(..., flush=True)` del detalle técnico (patrón de logging usado en el repo) y dejar que
   la UI muestre un mensaje genérico.

### 4.3 `app/pages/groceries_page.py` — botón de cámara + flujo

Dentro de `_render_smart_add()`, debajo del botón "Agregar a la lista":

1. **`ui.upload` oculto** que hace de puente con la cámara:

   ```python
   upload = (
       ui.upload(
           auto_upload=True,
           max_files=1,
           max_file_size=15_000_000,
           on_upload=handle_photo,
       )
       .props('accept="image/*"')
       .classes("hidden")
   )
   ```

2. **Botón visible** "Identificar con foto" (`icon="photo_camera"`, full-width, estilo
   `outline color=primary` para diferenciarlo del botón primario existente). El click debe
   dispararse **del lado del cliente** (mismo gesto del usuario — si el click al input pasa por
   el servidor, iOS/Safari puede bloquear la apertura de la cámara). Usar el `js_handler` de
   NiceGUI, que además fuerza el atributo `capture` sobre el input interno de QUploader (QUploader
   no expone `capture` como prop):

   ```python
   btn = ui.button("Identificar con foto", icon="photo_camera").classes("w-full").props(
       "outline color=primary"
   )
   btn.on("click", js_handler=f"""() => {{
       const up = document.getElementById('c{upload.id}');
       const input = up && up.querySelector('input[type=file]');
       if (input) {{
           input.setAttribute('accept', 'image/*');
           input.setAttribute('capture', 'environment');
           input.click();
       }}
   }}""")
   ```

   Notas de validación: en NiceGUI los elementos reciben id HTML `c{element.id}`; verifica que
   `element.on(..., js_handler=...)` existe en NiceGUI 2.7.0 (sí existe en la serie 2.x). Si algo
   difiere, el requisito invariable es: *el `input.click()` debe ejecutarse en el navegador dentro
   del mismo evento de click del usuario, con `capture=environment` puesto en el input*.

3. **Si `GEMINI_API_KEY` no está configurada** (chequeo server-side al renderizar): renderizar el
   botón deshabilitado con un caption debajo, p. ej. "Configura GEMINI_API_KEY para activar esta
   función" en texto pequeño gris. Así el fallo es obvio sin abrir la cámara.

4. **Handler `handle_photo` (async):**

   ```python
   async def handle_photo(e):
       image_bytes = e.content.read()          # e.content is a SpooledTemporaryFile
       mime = e.type or "image/jpeg"           # verify attr name in NiceGUI 2.7 (UploadEventArguments)
       upload.reset()                          # allow taking another photo later

       notification = ui.notification("Identificando artículo…", spinner=True, timeout=None)
       try:
           with get_db() as db:
               catalog_names = [i.name for i in search_suggestions(db, query="", limit=300)]
           name, category = await identify_grocery_from_photo(image_bytes, mime, catalog_names)
       except VisionNotConfigured:
           show_error("Falta configurar GEMINI_API_KEY en el servidor")
           return
       except VisionUnrecognized:
           show_error("No pude reconocer un producto en la foto. Intenta de nuevo o escríbelo manualmente.")
           return
       except VisionError:
           show_error("No se pudo identificar el artículo. Intenta de nuevo.")
           return
       finally:
           notification.dismiss()

       _show_photo_confirm_dialog(name, category, refresh_fn)
   ```

   Notas: el handler debe ser `async` para no bloquear el event loop de NiceGUI mientras Gemini
   responde. Verifica los nombres reales de los atributos del evento de upload en NiceGUI 2.7
   (`content`, `name`, `type`) y que `ui.notification(...)` con `.dismiss()` y `upload.reset()`
   existen en esa versión; si no, sustituye por un `ui.dialog` persistente con `ui.spinner`.

5. **Diálogo de confirmación `_show_photo_confirm_dialog(name, category, refresh_fn)`** — mismo
   estilo visual que `_show_category_dialog` existente:
   - Título: "Producto identificado".
   - Subtítulo pequeño gris: "Revisa el nombre y la categoría antes de agregar."
   - `ui.input` con el nombre propuesto (editable).
   - `ui.select(CATEGORIES)` con la categoría propuesta preseleccionada.
   - **Si el nombre propuesto ya existe en el catálogo** (comparación case-insensitive contra los
     nombres cargados), preseleccionar la **categoría real del catálogo** en lugar de la propuesta
     por Gemini, porque `add_to_active_list` conservará la del catálogo de todos modos (evita
     mostrar una categoría que luego no se aplica).
   - Botones "Cancelar" / "Agregar" (mismos estilos que el diálogo existente). "Agregar" valida
     que el nombre no esté vacío y llama a `_do_add(nombre, categoria, user_id, name_input, refresh_fn)`
     reutilizando la función existente (obtén `user_id` con `auth.current_user_id()` y redirige a
     `/login` si es `None`, igual que hace `add_item()`).

6. No modificar el flujo manual existente (input + autocomplete + diálogo de categoría): debe
   seguir funcionando idéntico.

### 4.4 `requirements.txt`

Agregar `httpx` **pineado a la versión que ya está instalada** como dependencia transitiva de
NiceGUI (ejecuta `pip show httpx` y usa esa versión, p. ej. `httpx==0.27.2`). Esto evita
conflictos de resolución con `nicegui==2.7.0`.

### 4.5 `.env.example`

Agregar al final, siguiendo el estilo de comentarios existente:

```
# Google Gemini API key used to identify grocery items from photos.
# Get one at https://aistudio.google.com/ → "Get API key".
GEMINI_API_KEY=change-me

# Optional: override the vision model (default: gemini-3-pro-preview).
#GEMINI_MODEL=gemini-3-pro-preview
```

### 4.6 `docker-compose.yml`

En la sección `environment` del servicio, agregar:

```yaml
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - GEMINI_MODEL=${GEMINI_MODEL:-}
```

⚠️ Nota: si `GEMINI_MODEL` llega como string vacío, `os.getenv("GEMINI_MODEL", "default")` NO
aplica el default (la variable existe pero vacía). En `vision_service.py` usa el patrón
`os.getenv("GEMINI_MODEL") or "gemini-3-pro-preview"`. Aplica el mismo cuidado con
`GEMINI_API_KEY` (string vacío = no configurada).

### 4.7 `README.md`

- En la sección **Compras (Grocery list)**: agregar un bullet describiendo la identificación por
  foto (botón, cámara, Gemini, diálogo de confirmación).
- En la tabla de **Configuration**: agregar filas para `GEMINI_API_KEY` (requerida para la
  función de foto; si falta, el botón aparece deshabilitado) y `GEMINI_MODEL` (opcional, default
  `gemini-3-pro-preview`).

## 5. Manejo de errores (resumen)

| Situación | Comportamiento |
|---|---|
| `GEMINI_API_KEY` ausente/vacía | Botón deshabilitado con caption explicativo; el servicio además lanza `VisionNotConfigured` como defensa |
| Foto sin producto identificable (`reconocido=false`) | Notificación: "No pude reconocer un producto en la foto…" |
| Error HTTP / timeout / respuesta malformada | Notificación genérica + detalle técnico a stdout (`print(..., flush=True)`) |
| Categoría devuelta fuera de la lista | Sustituir por `"Otros"` silenciosamente |
| Nombre ya en la lista activa | Sin cambios: `add_to_active_list` ya deduplica (no agrega dos veces) |
| Foto > 15 MB | Rechazada por `max_file_size` del uploader |

## 6. Qué NO hacer

- No agregar dependencias más allá de `httpx` (nada de `google-genai`, `Pillow`, etc.).
- No guardar la foto en disco ni en la base de datos.
- No exponer la API key al navegador (todo el llamado a Gemini es server-side).
- No cambiar el esquema de la base de datos ni los modelos.
- No tocar `app/mcp_server.py`, `app/admin.py` ni el flujo de tareas.
- No usar `getUserMedia` ni componentes de cámara en vivo (no hay HTTPS).
- No cambiar a otro proveedor de IA. Si el modelo `gemini-3-pro-preview` devolviera 404 (nombre
  retirado), deja el código configurable como está y repórtalo — el dueño puede fijar otro modelo
  vía `GEMINI_MODEL` sin tocar código.

## 7. Verificación y criterios de aceptación

Entorno de desarrollo: `pip install -r requirements.txt && python -m app.main`
(o `docker compose up -d --build`).

1. **Arranque:** la app inicia sin errores de import; `/groceries` renderiza con el botón nuevo.
2. **Sin API key:** el botón aparece deshabilitado con el caption explicativo. Nada crashea.
3. **Con API key** (`GEMINI_API_KEY` en el entorno): prueba el servicio de forma aislada con un
   pequeño script temporal que lea una imagen de prueba (puedes generar un PNG/JPEG simple) y
   llame a `identify_grocery_from_photo` con `asyncio.run(...)`; verifica que devuelve tupla o
   lanza `VisionUnrecognized` — ambas cosas son éxito (lo que importa es que la petición y el
   parseo funcionan). Si el entorno de implementación no tiene la key, deja este paso documentado
   como verificación manual del dueño y asegúrate de que los caminos de error están cubiertos.
4. **Flujo manual intacto:** agregar un artículo escribiendo (existente y nuevo) sigue
   funcionando igual que antes.
5. **Prueba end-to-end en teléfono** (la hará el dueño tras el deploy): tocar el botón abre la
   cámara directamente; tras la foto aparece el spinner, luego el diálogo con nombre/categoría;
   "Agregar" lo pone en la lista bajo la categoría correcta.

## 8. Entrega

Commits con mensajes descriptivos en presente (estilo del repo). Resume en el mensaje final:
archivos tocados, cómo configurar `GEMINI_API_KEY` en el VPS (`.env` + `docker compose up -d
--build`) y qué quedó pendiente de verificación manual en el teléfono.
