#!/bin/sh
# Run from any directory. Docker Desktop must be open and ready.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if command -v docker >/dev/null 2>&1; then
  docker_bin=$(command -v docker)
elif [ -x "$HOME/.docker/bin/docker" ]; then
  docker_bin="$HOME/.docker/bin/docker"
else
  echo 'Docker is not installed or not on PATH. Open docs/MAC_SETUP_GUIDE.md.' >&2
  exit 1
fi
if ! "$docker_bin" info >/dev/null 2>&1; then
  echo 'Cannot reach Docker. Open Docker Desktop, wait until ready, then run docker version in Terminal.' >&2
  exit 1
fi
if [ ! -e .env ]; then
  command -v openssl >/dev/null 2>&1 || { echo 'openssl is required to generate the local password.' >&2; exit 1; }
  local_password=$(openssl rand -hex 24)
  api_password=$(openssl rand -hex 24)
  # Restrict permissions from creation and refuse to overwrite a concurrent file.
  (umask 077; set -C; printf 'POSTGRES_PASSWORD=%s\nAPI_DATABASE_PASSWORD=%s\n' "$local_password" "$api_password" > .env)
  unset local_password api_password
  echo 'Created local configuration. Keep .env private.'
fi
# Existing installations retain the owner password and receive a separate API secret.
if ! grep -q '^API_DATABASE_PASSWORD=' .env; then
  command -v openssl >/dev/null 2>&1 || { echo 'openssl is required to generate the API password.' >&2; exit 1; }
  api_password=$(openssl rand -hex 24)
  chmod 600 .env
  printf '\nAPI_DATABASE_PASSWORD=%s\n' "$api_password" >> .env
  unset api_password
fi
if ! grep -q '^WORKER_DATABASE_PASSWORD=' .env; then
  command -v openssl >/dev/null 2>&1 || { echo 'openssl is required to generate the worker password.' >&2; exit 1; }
  worker_password=$(openssl rand -hex 24)
  chmod 600 .env
  printf '\nWORKER_DATABASE_PASSWORD=%s\n' "$worker_password" >> .env
  unset worker_password
fi
"$docker_bin" compose config --quiet
"$docker_bin" compose up --build -d
printf '\nNext: docker compose ps -a\nThen open http://localhost:8080 when db and api are healthy and web is running.\n'
