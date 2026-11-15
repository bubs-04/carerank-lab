#!/bin/sh
# Read-only diagnostics: no raw Compose configuration or credential output.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if command -v docker >/dev/null 2>&1; then
  docker_bin=$(command -v docker)
elif [ -x "$HOME/.docker/bin/docker" ]; then
  docker_bin="$HOME/.docker/bin/docker"
else
  echo 'Docker command not found.' >&2
  exit 1
fi
"$docker_bin" version
"$docker_bin" compose config --quiet
"$docker_bin" compose ps -a
curl --fail --show-error --silent --max-time 10 http://localhost:8000/api/health
printf '\n'
curl --fail --show-error --silent --max-time 10 http://localhost:8080/api/health
printf '\n'
"$docker_bin" compose exec -T db psql -U carerank -d carerank -c 'SELECT (SELECT count(*) FROM providers) AS providers, (SELECT count(*) FROM encounters) AS encounters, (SELECT count(*) FROM scores) AS scores;'
