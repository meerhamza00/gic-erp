#!/usr/bin/env bash
# Start the dev stack: containers, background worker, web server (http://localhost:8000).
# Safe to run repeatedly: it only starts what is not already running.
set -euo pipefail
# shellcheck source=dev/scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_docker
dc up -d

if in_bench "pgrep -f '[f]rappe.utils.bench_helper frappe worker' >/dev/null"; then
	echo "worker: already running"
else
	dc exec -d frappe bash -lc "cd $BENCH_IN_CONTAINER && exec bench worker > logs/dev-worker.log 2>&1"
	echo "worker: started (logs/dev-worker.log)"
fi

if in_bench "pgrep -f '[f]rappe.utils.bench_helper frappe serve' >/dev/null"; then
	echo "web: already running"
else
	dc exec -d frappe bash -lc "cd $BENCH_IN_CONTAINER && exec bench serve --port 8000 > logs/dev-web.log 2>&1"
	echo "web: starting (logs/dev-web.log)"
fi

port="${GIC_DEV_PORT:-8000}"
for _ in $(seq 1 30); do
	if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port/login")" = "200" ]; then
		echo "Ready: http://localhost:$port  (user: Administrator, password: dev/.secrets/admin_password)"
		exit 0
	fi
	sleep 2
done
echo "Web server did not answer in 60s. Check frappe-bench/logs/dev-web.log" >&2
exit 1
