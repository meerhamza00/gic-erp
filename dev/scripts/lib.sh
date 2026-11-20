#!/usr/bin/env bash
# Shared helpers for dev scripts. Source it; do not run it.
# shellcheck disable=SC2034  # variables are used by the scripts that source this file

DEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$(dirname "$DEV_DIR")"
BENCH_IN_CONTAINER=/workspace/development/frappe-bench

dc() {
	docker compose -f "$DEV_DIR/compose.yaml" "$@"
}

# Run a command inside the bench folder of the dev container.
in_bench() {
	dc exec -T frappe bash -lc "cd $BENCH_IN_CONTAINER && $1"
}

require_docker() {
	docker info >/dev/null 2>&1 || {
		echo "Docker is not running. Start Docker Desktop first." >&2
		exit 1
	}
}
