# Household App — Commands Cheat Sheet

A quick-reference guide to all the commands used to build, run, and deploy this app.
Bookmark this file. Update it as you learn new ones.

---

## 1. Daily Coding Workflow

Every coding session starts the same way:

```powershell
cd C:\Users\josue\Documents\household-app
.\.venv\Scripts\Activate.ps1
```

Your prompt should now show `(.venv) PS C:\...\household-app>`.

> If activation fails with "scripts disabled," run once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

---

## 2. Python & Project Setup

| Command | What it does | When to use |
|---------|--------------|-------------|
| `python -m venv .venv` | Create the virtual environment | Once, when setting up the project |
| `.\.venv\Scripts\Activate.ps1` | Activate the venv (Windows PowerShell) | Every new terminal session |
| `deactivate` | Exit the venv | When done coding |
| `pip install -r requirements.txt` | Install all dependencies | After cloning the repo or when deps change |
| `pip install <package>` | Install one package | When adding a new dependency |
| `pip freeze > requirements.txt` | Save current package versions | After installing new packages (be careful!) |
| `pip list` | Show installed packages | To check what's installed |

---

## 3. Running the App Locally (No Docker)

| Command | What it does |
|---------|--------------|
| `python -m app.main` | Start the NiceGUI server on http://localhost:8080 |
| `python -m app.seed` | Populate the DB with test users, tasks, groceries |
| `python -m sanity_test` | Run a quick health check on the DB |

Stop the server with **`Ctrl+C`**.

> **Important:** all `python -m` commands must be run from the project root
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
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 10. Common Workflow Examples

### "I edited some Python code, what do I do?"

**Local (no Docker):**
1. `Ctrl+C` to stop the server
2. `python -m app.main` to restart

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
python -m app.seed     # recreate with sample data
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
| `ModuleNotFoundError: No module named 'X'` | Venv not activated, or wrong folder | `.\.venv\Scripts\Activate.ps1` and check `pwd` |
| `(.venv)` missing from prompt | Venv not activated | `.\.venv\Scripts\Activate.ps1` |
| `ImportError: cannot import name 'X'` | File got truncated, or typo in name | Re-check file content, restart server |
| Code change does nothing | Server still running old code | Stop & restart; clear `__pycache__` |
| `error: remote origin already exists` | Remote URL already set | `git remote set-url origin <new-url>` |
| `git push` does nothing visible | Auth needed | Use Personal Access Token, not password |
| Tasks don't show as completed | Timezone mismatch | Already fixed — but check `LOCAL_TZ` in code |
| Docker container won't start | Port 8080 in use | `docker ps`, stop other container, or change port |
| `DetachedInstanceError` from SQLAlchemy | Used a model object after session closed | Copy data to plain dict/tuple before exit |

---

## 12. URLs to Remember

- **App locally:** http://localhost:8080
- **App on phone (same WiFi):** http://YOUR-PC-IP:8080 (find with `ipconfig`)
- **GitHub repo:** https://github.com/josue2es/household-app
- **GitHub tokens:** https://github.com/settings/tokens
- **NiceGUI docs:** https://nicegui.io/documentation
- **Quasar components:** https://quasar.dev/vue-components
- **SQLAlchemy docs:** https://docs.sqlalchemy.org/en/20/

---

## 13. Added Admin CLI
Run:
docker compose exec household-app python -m app.admin

*Last updated: as the project evolves. Add new commands as you learn them.*
