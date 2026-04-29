# syntax=docker/dockerfile:1

# ---- Step 1: Pick a base image ----
# We start from a small official Python image that runs Linux.
# "slim" means it has Python but very little else — keeps the image small.
FROM python:3.12-slim

# ---- Step 2: Set the working directory ----
# All commands below run from /app inside the container.
WORKDIR /app

# ---- Step 3: Install Python dependencies ----
# We copy requirements.txt first (before all the code) so Docker can
# cache this expensive step. If only your code changes, Docker reuses
# the cached pip-install layer instead of reinstalling everything.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Step 4: Copy your application code ----
# This copies the `app/` folder into /app/app inside the container.
COPY app/ ./app/
COPY start.sh .

# ---- Step 5: Tell Docker which ports the app listens on ----
# 8080 = NiceGUI web app, 8081 = MCP server (SSE transport)
EXPOSE 8080 8081

# ---- Step 6: The command that starts both processes ----
# start.sh launches the MCP server in the background then the NiceGUI
# app in the foreground. The container stays alive as long as NiceGUI runs.
CMD ["bash", "start.sh"]