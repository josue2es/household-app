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
| UI framework | [NiceGUI](https://nicegui.io/) 2.7.0 (Python, renders Quasar/Vue in the browser) |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (single file at `data/household.db`) |
| Auth | bcrypt password hashing + NiceGUI browser session storage |
| Deployment | Docker + Docker Compose |

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

The app will be available at **http://localhost:8080**.

The SQLite database is stored in `./data/household.db` on the host (mounted into the container). It persists across container restarts and rebuilds.

### Locally (no Docker)

```bash
pip install -r requirements.txt
python -m app.main
```

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `STORAGE_SECRET` | `dev-secret-change-me` | Secret used to sign NiceGUI browser sessions. **Change this in production.** |

Set it in a `.env` file at the project root:

```
STORAGE_SECRET=some-long-random-string
```

### Timezone

The app uses a hardcoded UTC−6 offset to determine which tasks are due today and to display completion times. If your household is in a different timezone, update `LOCAL_TZ` in `app/services/task_service.py`:

```python
LOCAL_TZ = timezone(timedelta(hours=-6))  # change -6 to your UTC offset
```

---

## Admin CLI

An interactive command-line tool for managing the app's data without going through the web UI. Run it inside the container:

```bash
docker compose exec household-app python -m app.admin
```

Or locally:

```bash
python -m app.admin           # skip mode: existing records are left unchanged
python -m app.admin --update  # update mode: existing records are overwritten on import
```

### Main menu

```
1. Manage users
2. List all groceries
3. List all tasks
4. Import grocery items from CSV
5. Import tasks from CSV
6. Export current data to CSV
```

### User management

New users must be created through the CLI (there is no sign-up page):

```
1. Manage users → 2. Create new user
```

You will be prompted for a name, an avatar color, and a password (minimum 6 characters, entered twice for confirmation).

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
python -m app.main  # tables are recreated automatically on startup
```

```bash
# Linux / macOS
rm data/household.db
python -m app.main
```
