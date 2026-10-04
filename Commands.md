# Household App — Commands Cheat Sheet

A quick-reference guide to all the commands used to build, run, and deploy this app.
Bookmark this file. Update it as you learn new ones.

---

## 1. Daily Coding Workflow

Every coding session starts the same way:

```powershell
cd C:\Users\josue\Documents\household-app
```

That's it — no need to activate the virtual environment. Prefix commands with
`uv run` (e.g. `uv run python -m app.main`) and uv runs them inside `.venv` for you,
installing any missing or changed dependencies first.

> Prefer an activated shell, so plain `python` uses the venv? `.\.venv\Scripts\Activate.ps1`
> still works. If activation fails with "scripts disabled," run once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

---

## 2. Python & Project Setup (uv)

Dependencies live in `pyproject.toml`; `uv.lock` records the exact version of every package.
Docker builds from `uv.lock` too, so local and production always match.

| Command | What it does | When to use |
|---------|--------------|-------------|
| `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | Install uv | Once per machine |
| `uv sync` | Create `.venv` (Python 3.12) and install the exact versions from `uv.lock` | After cloning the repo (optional — `uv run` does it too) |
| `uv run <command>` | Run a command inside `.venv` | Every time you run the app or a script |
| `uv add <package>` | Add a dependency (updates `pyproject.toml` and `uv.lock`) | When adding a new dependency |
| `uv remove <package>` | Remove a dependency | When a package is no longer needed |
| `uv lock --upgrade-package <package>` | Upgrade one package to the newest allowed version | When you want a newer version |
| `uv pip list` | Show installed packages | To check what's installed |
| `uv tree` | Show which package depends on which | To see why a package is installed |

> Always commit `pyproject.toml` and `uv.lock` together. Never edit `uv.lock` by hand.

---

## 3. Running the App Locally (No Docker)

| Command | What it does |
|---------|--------------|
| `uv run python -m app.main` | Start the NiceGUI server on http://localhost:8080 |
| `uv run python -m app.admin` | Open the Admin CLI |
| `uv run python -m sanity_test` | Run a quick health check on the DB |

Stop the server with **`Ctrl+C`**.

> **Important:** all `uv run python -m` commands must be run from the project root
> (`C:\Users\josue\Documents\household-app`), not from inside `app\`.

---

## 4. Useful File / Cache Commands (Windows PowerShell)

| Command | What it does |
|---------|--------------|
| `dir` | List files in current folder |
| `dir app` | List files in `app/` folder |
| `cd ..` | Go up one folder |
| `pwd` | Show current folder |
| `type file.py` | Print contents of a file |
| `type file.py \| Select-String "pattern"` | Search for text in a file |
| `Remove-Item app\__pycache__ -Recurse -Force` | Clear Python's compiled cache (when changes don't take effect) |
| `Rename-Item old.py new.py` | Rename a file |
| `Move-Item file.py folder\` | Move a file |

---

## 5. Git — Local Repository

| Command | What it does |
|---------|--------------|
| `git status` | Show what's changed (most-used command) |
| `git diff` | Show line-by-line changes in modified files |
| `git add .` | Stage all changes for commit |
| `git add file.py` | Stage just one file |
| `git commit -m "message"` | Save staged changes as a snapshot |
| `git log --oneline` | Show commit history (compact) |
| `git log` | Show full commit history |
| `git restore file.py` | Discard local changes to a file |

---

## 6. Git — GitHub (Remote)

| Command | What it does |
|---------|--------------|
| `git remote -v` | Show configured remotes |
| `git remote set-url origin <url>` | Change the remote URL |
| `git push` | Upload commits to GitHub |
| `git push -u origin main` | First-time push (sets up the link) |
| `git pull` | Download latest commits from GitHub |
| `git clone <url>` | Copy a repo to your machine (used on VPS) |

> Authentication uses a **Personal Access Token** (not password).
> Generate one at: https://github.com/settings/tokens

---

## 7. Docker — Building & Running

| Command | What it does |
|---------|--------------|
| `docker --version` | Check Docker is installed |
| `docker images` | List built images |
| `docker ps` | List running containers |
| `docker ps -a` | List ALL containers (including stopped) |
| `docker build -t household-app .` | Build image from Dockerfile in current folder |
| `docker rmi household-app` | Delete an image |
| `docker rm <container-name>` | Delete a stopped container |
| `docker stop <container-name>` | Stop a running container |
| `docker logs household-app` | View the app's logs |
| `docker exec -it household-app sh` | Open a shell INSIDE the running container (great for debugging) |

### Manual run (the long way — used in Step 4b)

```powershell
docker run --rm -p 8080:8080 -v ${PWD}/data:/app/data -e STORAGE_SECRET=dev-secret household-app
```

---

## 8. Docker Compose — The Easy Way

Always run from the project root (where `docker-compose.yml` lives).

| Command | What it does |
|---------|--------------|
| `docker compose up` | Start the app, stream logs to terminal |
| `docker compose up -d` | Start in background (detached mode) |
| `docker compose up -d --build` | Rebuild image and start (use after code changes) |
| `docker compose down` | Stop and remove the container |
| `docker compose ps` | Show what's running |
| `docker compose logs -f` | Stream live logs (Ctrl+C exits log view, container keeps running) |
| `docker compose restart` | Restart without rebuilding |
| `docker compose exec household-app sh` | Open a shell inside the running container |

> Stop with **`Ctrl+C`** when running in the foreground (without `-d`).

---

## 9. Generating a Secure Secret

Used for the `STORAGE_SECRET` in `.env`:

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 10. Common Workflow Examples

### "I edited some Python code, what do I do?"

**Local (no Docker):**
1. `Ctrl+C` to stop the server
2. `uv run python -m app.main` to restart

**Docker:**
1. `docker compose up -d --build`

### "I want to commit my changes to GitHub"

```powershell
git status              # see what changed
git add .               # stage everything
git commit -m "Brief message in present tense"
git push
```

### "Code change isn't taking effect"

1. Make sure you saved the file
2. Stop & restart the server (Python doesn't hot-reload by default)
3. Hard-refresh browser: `Ctrl+Shift+R`
4. If still stuck: `Remove-Item app\__pycache__ -Recurse -Force`
5. For Docker: don't forget `--build` flag

### "Database looks weird, I want to start fresh"

```powershell
# Stop the server first!
Remove-Item data\household.db
uv run python -m app.main     # restart — tables are recreated automatically
```

### "I want to deploy a new version to the VPS"

(Once we set up the VPS in upcoming steps)
```bash
ssh your-vps
cd household-app
git pull
docker compose up -d --build
```

---

## 11. Troubleshooting Quick Reference

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: No module named 'X'` | Ran plain `python` instead of `uv run python`, or wrong folder | Use `uv run python ...` and check `pwd` is the project root |
| `The lockfile at uv.lock needs to be updated` (Docker build) | `pyproject.toml` changed but `uv.lock` wasn't updated or committed | `uv lock`, then commit `uv.lock` |
| `ImportError: cannot import name 'X'` | File got truncated, or typo in name | Re-check file content, restart server |
| Code change does nothing | Server still running old code | Stop & restart; clear `__pycache__` |
| `error: remote origin already exists` | Remote URL already set | `git remote set-url origin <new-url>` |
| `git push` does nothing visible | Auth needed | Use Personal Access Token, not password |
| Tasks don't show as completed | Timezone mismatch | Already fixed — but check `LOCAL_TZ` in code |
| Docker container won't start | Host port 8090 (or 8091) in use | `docker ps`, stop other container, or change the host port in `docker-compose.yml` |
| `DetachedInstanceError` from SQLAlchemy | Used a model object after session closed | Copy data to plain dict/tuple before exit |

---

## 12. URLs to Remember

- **App locally:** http://localhost:8080 (or the `APP_PORT` set in `.env`)
- **App on phone (same WiFi):** http://YOUR-PC-IP:8080 (find with `ipconfig`)
- **GitHub repo:** https://github.com/josue2es/household-app
- **GitHub tokens:** https://github.com/settings/tokens
- **NiceGUI docs:** https://nicegui.io/documentation
- **uv docs:** https://docs.astral.sh/uv/
- **Quasar components:** https://quasar.dev/vue-components
- **SQLAlchemy docs:** https://docs.sqlalchemy.org/en/20/

---

## 13. Added Admin CLI
Run:
docker compose exec household-app python -m app.admin

*Last updated: as the project evolves. Add new commands as you learn them.*
