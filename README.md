# Household App

A mobile-first web app for managing household chores and the grocery shopping list. Designed to be used from a phone browser.

Built with Python, [NiceGUI](https://nicegui.io/), and SQLite. Deployed via Docker.

---

## Features

### Tareas (Chores)

Track recurring and one-off household tasks. The dashboard shows only what is due today, divided into two sections:

- **Pendientes (Hoy)** — tasks tied to a specific date or day of the week/month.
- **Pendientes (Libre)** — flexible tasks with no fixed day; they appear every day until completed within their period.

Completed tasks stay visible below the pending sections (greyed out with strikethrough) and can be reactivated with a single tap if marked by mistake.

#### Frequency types

| Type | Description |
|---|---|
| `Diario` | Appears every day |
| `Semanal (día específico)` | Appears on one chosen weekday |
| `Días específicos de la semana` | Appears on a set of chosen weekdays |
| `Mensual (día específico)` | Appears on a specific day of the month |
| `Una sola vez` | Appears on a single date, then never again |
| `Semanal (cualquier día)` | Appears every day until completed once this week (Mon–Sun) |
| `Mensual (cualquier día)` | Appears every day until completed once this calendar month |
| `Bimestral (cualquier día)` | Appears every day until completed once in the current two-month block (Jan–Feb, Mar–Apr, …) |
| `Cada X días` | Appears every day; once completed, disappears for exactly X days then reappears |

Every completion is recorded in the database with a timestamp and the user who did it, giving a full audit trail.

---

### Compras (Grocery list)

A shared shopping list with a smart search field.

- Type to search items already in the catalog (autocomplete). The catalog is sorted by how often each item has been purchased, so frequently bought items appear first.
- If you type a name not in the catalog, a dialog asks for the category before saving it as a new item.
- Items are grouped by category on the list.
- Tap the circle to mark an item as purchased (increments its purchase count for future sorting).
- Use the ⋮ menu to remove an item without marking it purchased.
- Tap **Identificar con foto** to open the phone's camera, take a photo of a product, and let Gemini identify its name and category. A confirmation dialog lets you review/edit both before adding it to the list. Requires `GEMINI_API_KEY` to be configured; the button is disabled otherwise.

#### Categories

| Category | Examples |
|---|---|
| Despensa | Rice, beans, coffee, oil |
| Frescos | Tomatoes, onions, plantains, avocados |
| Carnes y Lácteos | Eggs, cheese, milk, chicken |
| Panadería | Tortillas, French bread, sweet bread |
| Cuidado Personal | Toilet paper, shampoo, toothpaste |
| Limpieza del Hogar | Detergent, broom, dish soap |
| Mascotas | Pet food |
| Otros | Batteries, matches, lightbulbs |

---

## Tech stack

| Layer | Technology |
|---|---|
| UI framework | [NiceGUI](https://nicegui.io/) 3 (Python, renders Quasar/Vue in the browser) |
| ORM | SQLAlchemy 2.1 |
| Database | SQLite (single file at `data/household.db`) |
| Auth | bcrypt password hashing + NiceGUI browser session storage |
| Vision AI | Google Gemini API (`gemini-3-pro-preview`) — identifies grocery items from a photo |
| Dependencies | [uv](https://docs.astral.sh/uv/) — declared in `pyproject.toml`, pinned in `uv.lock`; used both locally and in the Docker image |
| Deployment | Docker + Docker Compose, or systemd services (`deploy/`) |

---

## Running the app

### With Docker (recommended)

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

The app will be available at **http://localhost:8090** (`docker-compose.yml` maps host port 8090 to the container's port 8080).

The SQLite database is stored in `./data/household.db` on the host (mounted into the container). It persists across container restarts and rebuilds.

### Locally (no Docker)

Local development uses [uv](https://docs.astral.sh/uv/) to manage the Python version, the virtual environment, and dependencies. Install it once by following the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

```bash
# Create .venv with Python 3.12 (from .python-version, same as the Docker image)
# and install the exact dependency versions recorded in uv.lock.
# uv downloads Python 3.12 automatically if it isn't installed.
uv sync

# Start the app
uv run python -m app.main
```

The app will be available at **http://localhost:8080**. To use a different port, set `APP_PORT` in `.env` (see [Configuration](#configuration)).

`uv run` executes the command inside the project's `.venv`, so there is no need to activate the virtual environment first. It also syncs `.venv` with `uv.lock` before running, so after a `git pull` that changed dependencies you don't need to remember to run `uv sync`. Run all commands from the project root.

#### Managing dependencies

Dependencies are declared in `pyproject.toml`, and `uv.lock` records the exact version of every package (including sub-dependencies) so that local installs and the Docker image are identical. Don't edit `uv.lock` by hand; commit both files whenever they change.

| Command | What it does |
|---|---|
| `uv add <package>` | Add a dependency to `pyproject.toml`, update `uv.lock`, and install it |
| `uv remove <package>` | Remove a dependency |
| `uv lock --upgrade-package <package>` | Upgrade one package to the newest version allowed by `pyproject.toml` |
| `uv tree` | Show the dependency tree |

### As a systemd service (Linux, no Docker)

To keep the app running in the background on a Linux machine without Docker (starting on boot and restarting if it crashes), use the two unit files in `deploy/`:

| Unit | Runs | Port |
|---|---|---|
| `household-app.service` | The web app | `APP_PORT` (default 8080) |
| `household-app-mcp.service` | The [MCP server](#mcp-server-ai-agent-access) in SSE mode | `MCP_PORT` (default 8081) |

Both run as your own user from the repo folder in your home directory, and read their settings from the same `.env`.

```bash
# 1. Install uv (then open a new terminal so `uv` is on your PATH)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Get the code and install the dependencies
git clone https://github.com/josue2es/household-app.git ~/household-app
cd ~/household-app
uv sync --locked --no-dev

# 3. Settings: create .env and replace every "change-me" (STORAGE_SECRET,
#    MCP_API_KEY, ...). Add APP_PORT / MCP_PORT for non-default ports.
cp .env.example .env
nano .env
chmod 600 .env   # it holds secrets: readable only by you

# 4. Install both units, filling in your user and this folder
for unit in household-app household-app-mcp; do
  sed -e "s|/home/YOUR_USER/household-app|$PWD|g" -e "s|YOUR_USER|$USER|g" \
    deploy/$unit.service | sudo tee /etc/systemd/system/$unit.service > /dev/null
done

# 5. Start both now and on every boot
sudo systemctl daemon-reload
sudo systemctl enable --now household-app household-app-mcp
```

Then the web app is at `http://<machine-ip>:<APP_PORT>` and the MCP server at `http://<machine-ip>:<MCP_PORT>/sse` (with the `Authorization: Bearer <MCP_API_KEY>` header). The two ports must be different. Don't need the MCP server? Leave `household-app-mcp` out of step 5.

Everyday commands:

| Command | What it does |
|---|---|
| `sudo systemctl status household-app household-app-mcp` | Are they running? Shows the last log lines too |
| `journalctl -u household-app -u household-app-mcp -f` | Follow the logs live (`Ctrl+C` to exit) |
| `sudo systemctl restart household-app household-app-mcp` | Restart, e.g. after editing `.env` |
| `sudo systemctl disable --now household-app household-app-mcp` | Stop them and don't start them on boot anymore |

To update to the latest code:

```bash
cd ~/household-app
git pull
uv sync --locked --no-dev
sudo systemctl restart household-app household-app-mcp
```

If an update changes the files in `deploy/` (or you move the repo folder), repeat steps 4 and 5. The [Admin CLI](#admin-cli) works as usual: `uv run python -m app.admin` from the repo folder.

### HTTPS with Caddy (and Cloudflare)

Both servers speak plain HTTP. To serve them over HTTPS, put [Caddy](https://caddyserver.com/) in front: it gets and renews the certificate for your domain automatically. One hostname is enough for both, because the MCP server only uses the paths `/sse` and `/messages/`, which the web app never uses.

1. In `.env`, make both apps listen only on this machine, so they can't be reached directly over plain HTTP (bypassing Caddy), and set the MCP token:

   ```
   APP_HOST=127.0.0.1
   MCP_HOST=127.0.0.1
   MCP_API_KEY=some-long-random-string
   ```

   Then `sudo systemctl restart household-app household-app-mcp`.

2. Add a site block to your Caddyfile (usually `/etc/caddy/Caddyfile`), using your domain and your `APP_PORT` / `MCP_PORT`:

   ```
   hogar.example.com {
   	# MCP server: the SSE stream and the endpoint clients POST messages to
   	@mcp path /sse /messages/*
   	handle @mcp {
   		reverse_proxy localhost:8081
   	}

   	# Everything else: the web app
   	handle {
   		reverse_proxy localhost:8080
   	}
   }
   ```

   Then `sudo systemctl reload caddy`.

3. The web app is at `https://hogar.example.com`, and MCP clients connect to `https://hogar.example.com/sse` with the `Authorization: Bearer <MCP_API_KEY>` header.

Keep `/sse` and `/messages/*` at the root of the domain: the MCP server tells clients to send their messages to `/messages/`, so serving it under a prefix such as `/mcp/sse` breaks it. The server pings the stream every 15 seconds, which keeps it open through proxies with idle timeouts (Cloudflare's is 100 seconds).

**With Cloudflare's proxy** (orange cloud) in front of Caddy:
- A separate hostname for the MCP server is optional. If you want one, keep it one level below your domain (`hogar-mcp.example.com`, not `mcp.hogar.example.com`): Cloudflare's free certificate only covers `*.example.com`.
- MCP clients aren't browsers, so Cloudflare's bot protection (Bot Fight Mode, challenges) can block them. If a client gets a 403 or an HTML challenge page, add a WAF custom rule that skips those protections for the paths `/sse` and `/messages/`.

**With Docker** instead of systemd, the containers already listen on `0.0.0.0` inside, so restrict the published ports instead: in `docker-compose.yml`, change them to `"127.0.0.1:8090:8080"` and `"127.0.0.1:8091:8081"`, and point Caddy at `localhost:8090` and `localhost:8091`. (Docker's published ports bypass `ufw`, so a firewall rule alone isn't enough.)

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `STORAGE_SECRET` | `dev-secret-change-me` | Secret used to sign NiceGUI browser sessions. **Change this in production.** |
| `MCP_API_KEY` | *(none)* | Bearer token required to connect to the [MCP server](#mcp-server-ai-agent-access) when it runs in SSE mode (Docker/VPS). Leave unset to run it unauthenticated; it then only accepts requests addressed to `localhost`, so remote clients can't connect. |
| `GEMINI_API_KEY` | *(none)* | Google Gemini API key used for the "Identificar con foto" grocery feature. Get one at [aistudio.google.com](https://aistudio.google.com/). If unset, the photo button is disabled. |
| `GEMINI_MODEL` | `gemini-3-pro-preview` | Gemini model used to identify products from photos. |
| `APP_HOST` | `0.0.0.0` | Network address the web app listens on when run without Docker. `0.0.0.0` accepts connections from other devices (e.g. your phone on the same Wi-Fi); `127.0.0.1` accepts only this machine, which is what you want [behind Caddy](#https-with-caddy-and-cloudflare). Docker ignores it. |
| `APP_PORT` | `8080` | Port the web app listens on when run without Docker (locally with `uv run python -m app.main`, or as a [systemd service](#as-a-systemd-service-linux-no-docker)). Docker ignores it: the container always uses 8080 inside, and the host port (8090) is set in `docker-compose.yml`. |
| `MCP_HOST` | `0.0.0.0` | Network address of the MCP server in SSE mode when run without Docker. Set `127.0.0.1` [behind Caddy](#https-with-caddy-and-cloudflare). Docker ignores it. |
| `MCP_PORT` | `8081` | Port of the [MCP server](#mcp-server-ai-agent-access) in SSE mode when run without Docker (the `household-app-mcp` systemd service). Must differ from `APP_PORT`. Docker ignores it: the host port (8091) is set in `docker-compose.yml`. |

Set them in a `.env` file at the project root (copy `.env.example` to start). Both ways of running the app read it: Docker Compose passes the values into the container, and a local run loads the file at startup. A variable already set in your shell takes priority over `.env`.

```
STORAGE_SECRET=some-long-random-string
MCP_API_KEY=some-long-random-string
GEMINI_API_KEY=your-gemini-api-key
APP_PORT=8085
```

### Timezone

The app uses a hardcoded UTC−6 offset to determine which tasks are due today and to display completion times. If your household is in a different timezone, update `LOCAL_TZ` in `app/services/task_service.py`:

```python
LOCAL_TZ = timezone(timedelta(hours=-6))  # change -6 to your UTC offset
```

---

## MCP Server (AI agent access)

Besides the web UI, the app runs a second server that exposes tasks and the shopping list as [MCP](https://modelcontextprotocol.io/) tools, so an AI agent (Claude Desktop, Claude Code, etc.) can read and manage them without opening the browser. Source: `app/mcp_server.py`.

It supports two transport modes, controlled by the `MCP_TRANSPORT` env var:

| Mode | When it's used | How a client connects |
|---|---|---|
| `stdio` (default) | Local development — the MCP client launches the server itself as a subprocess | Point the client at `uv run --directory /path/to/household-app python -m app.mcp_server` |
| `sse` | Server deployments, alongside the web app — Docker (`start.sh`) or the [`household-app-mcp` systemd service](#as-a-systemd-service-linux-no-docker) | SSE endpoint `http://<host>:8091/sse` with Docker (host port from `docker-compose.yml`), or `http://<host>:<MCP_PORT>/sse` with systemd (default 8081); header `Authorization: Bearer <MCP_API_KEY>` |

In `stdio` mode, `--directory` makes uv switch to the project folder before running, so it finds the project's `.venv` no matter which folder the MCP client starts in. In a client's JSON config this looks like:

```json
{
  "mcpServers": {
    "household-app": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/household-app", "python", "-m", "app.mcp_server"]
    }
  }
}
```

### Available tools

| Tool | Purpose |
|---|---|
| `list_pending_tasks` | Tasks due today (scheduled + flexible) |
| `list_completed_tasks` | Tasks completed today, with who and when |
| `complete_task(task_id, user_name)` | Mark a task done |
| `add_task(name, frequency_type, frequency_value, description)` | Create a task (same frequency types as the Admin CLI) |
| `delete_task(task_id)` | Soft-deactivate a task |
| `get_shopping_list` | Items currently pending on the shopping list |
| `add_to_shopping_list(item_name, user_name)` | Add an item (new items default to category "Otros") |
| `mark_item_purchased(entry_id)` | Mark an item as bought |
| `remove_from_shopping_list(entry_id)` | Remove an item without marking it purchased |

### Enabling it on a VPS

1. Set `MCP_API_KEY` in `.env` (see [Configuration](#configuration)).
2. `docker compose up -d --build` — this starts the SSE server on container port 8081, published as host port **8091**.
3. Configure your MCP client with the SSE URL `http://<vps-host>:8091/sse` and the token as the `Authorization: Bearer` header.

That URL is plain HTTP, so the token travels unencrypted. On a server reachable from the internet, serve it over HTTPS instead: see [HTTPS with Caddy](#https-with-caddy-and-cloudflare).

If you don't use an MCP client, this server just runs in the background and can be ignored.

---

## Admin CLI

An interactive command-line tool for managing the app's data without going through the web UI. Run it inside the container:

```bash
docker compose exec household-app python -m app.admin
```

Or locally:

```bash
uv run python -m app.admin           # skip mode: existing records are left unchanged
uv run python -m app.admin --update  # update mode: existing records are overwritten on import
```

### Main menu

```
1. Manage users
2. Manage groceries
3. Manage tasks
4. Import grocery items from CSV
5. Import tasks from CSV
6. Export current data to CSV
```

### User management

New users must be created through the CLI (there is no sign-up page):

```
1. Manage users → 2. Create new user
```

You will be prompted for a name, an avatar color, and a password (minimum 6 characters and maximum 72 bytes — accented letters like ñ count as 2 — entered twice for confirmation).

#### User submenu options

| Option | Description |
|---|---|
| List all users | Table of all users with ID, name, color, and creation date |
| Create new user | Prompts for name, avatar color, and password |
| Change user password | Pick a user and set a new password |
| Edit user | Change name and/or avatar color |
| Delete user | Permanently deletes the user (completion history becomes orphaned) |

### Grocery management

```
2. Manage groceries
```

| Option | Description |
|---|---|
| List all groceries | Table sorted by category, showing ID, name, category, and purchase count |
| Add grocery item | Enter name, pick a category, optionally set purchase count |
| Edit grocery item | Change name, category, and/or purchase count |
| Delete grocery item | Permanently removes the item; warns if it is currently on the shopping list |

### Task management

```
3. Manage tasks
```

| Option | Description |
|---|---|
| List all tasks | Table of all active tasks with name, frequency, and description |
| Add task | Enter name, description, and choose frequency type with interactive prompts |
| Edit task | Change name, description, and/or frequency |
| Delete task | Soft-deactivates the task (completion history is preserved) |

When adding or editing a task you will be guided through all frequency options:

```
 1. Diario
 2. Semanal (día específico)        → pick weekday
 3. Días específicos de la semana   → pick one or more weekdays
 4. Mensual (día específico)        → enter day of month
 5. Una sola vez (fecha específica) → enter YYYY-MM-DD date
 6. Semanal (cualquier día)
 7. Mensual (cualquier día)
 8. Bimestral (cualquier día)
 9. Cada X días                     → enter number of days
```

### CSV import — grocery items

```
name,category,purchase_count
Café,Despensa,15
Leche,Carnes y Lácteos,12
```

Valid categories: `Despensa`, `Frescos`, `Carnes y Lácteos`, `Panadería`, `Cuidado Personal`, `Limpieza del Hogar`, `Mascotas`, `Otros`.

### CSV import — tasks

```
name,description,frequency_type,frequency_value
Tender la cama,Cada mañana,daily,
Sacar la basura,Martes y viernes,specific_days,"1,4"
Pagar renta,El día 1 de cada mes,monthly,1
Revisar el jardín,Una vez a la semana,weekly_any,
Cambiar filtro del agua,Cada 60 días,every_x_days,60
```

`frequency_value` depends on `frequency_type`:

| frequency_type | frequency_value |
|---|---|
| `daily` | *(leave empty)* |
| `weekly` | Weekday number: 0 = Monday … 6 = Sunday |
| `specific_days` | Comma-separated weekday numbers, e.g. `1,4` |
| `monthly` | Day of month, e.g. `1` |
| `once` | Date in `YYYY-MM-DD` format |
| `weekly_any` | *(leave empty)* |
| `monthly_any` | *(leave empty)* |
| `bimonthly_any` | *(leave empty)* |
| `every_x_days` | Number of days, e.g. `14` |

### CSV export

Exports three files to a timestamped folder:

```
exports/
  household_export_2026-04-28_10-30-00/
    users.csv
    groceries.csv
    tasks.csv
```

The export format is compatible with the importers, so data can be round-tripped (migrated, backed up, and restored).

---

## Importing CSV files into the Docker container

The container only mounts the `./data` folder. Place your CSV files there and reference them by their container path:

```bash
# On the host, copy the file into the data folder
cp my-tasks.csv ./data/

# Then in the CLI
Path to CSV file: /app/data/my-tasks.csv
```

---

## Database

SQLite file: `data/household.db`

### Schema overview

| Table | Purpose |
|---|---|
| `users` | App users with bcrypt-hashed passwords and avatar colors |
| `tasks` | Task definitions (name, frequency type, frequency config as JSON) |
| `task_logs` | Immutable completion records (task, user, timestamp) |
| `grocery_items` | Item catalog with purchase counts for autocomplete sorting |
| `active_shopping_items` | Current shopping list (pending and purchased entries) |

Completed tasks are **never deleted** from `task_logs` — the full history is always queryable. Tasks themselves use soft-delete (`is_active = false`) to preserve the log trail.

To reset the database (start fresh):

```powershell
# Windows
Remove-Item data\household.db
uv run python -m app.main  # tables are recreated automatically on startup
```

```bash
# Linux / macOS
rm data/household.db
uv run python -m app.main
```
