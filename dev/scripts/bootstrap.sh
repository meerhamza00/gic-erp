#!/usr/bin/env bash
# New machine: build a complete dev workspace around a fresh copy of this repo.
#
#   git clone https://github.com/meerhamza00/gic-erp.git /tmp/gic-erp
#   /tmp/gic-erp/dev/scripts/bootstrap.sh ~/gicnext
#
# Creates <workspace>/development/frappe-bench with Frappe + ERPNext at the versions in
# deploy/versions.conf, clones this repo into apps/gic_erp, generates random dev
# passwords, and creates two sites: gic-dev.local (for you) and gic-test.local (for tests).
# Takes 15-25 minutes on the first run. Needs Docker and git.
set -euo pipefail

workspace="${1:?Usage: bootstrap.sh <workspace-dir>}"
src="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
source "$src/deploy/versions.conf"

docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
mkdir -p "$workspace/development"
workspace="$(cd "$workspace" && pwd)"
bench_dir="$workspace/development/frappe-bench"
app="$bench_dir/apps/gic_erp"

if [ -e "$bench_dir" ]; then
	echo "$bench_dir already exists. Pick an empty workspace." >&2
	exit 1
fi

echo "==> bench init (Frappe $FRAPPE_REF)"
docker run --rm -v "$workspace/development:/workspace/development" -w /workspace/development \
	frappe/bench:latest bash -lc \
	"bench init --frappe-branch $FRAPPE_REF --skip-redis-config-generation --no-backups frappe-bench"

echo "==> clone gic_erp into the bench"
git clone --quiet "$src" "$app"
origin="$(git -C "$src" remote get-url origin 2>/dev/null || true)"
[ -n "$origin" ] && git -C "$app" remote set-url origin "$origin"

echo "==> dev passwords (random, dev/.secrets, gitignored)"
mkdir -p "$app/dev/.secrets"
chmod 700 "$app/dev/.secrets"
for f in db_root_password admin_password; do
	openssl rand -base64 24 | tr -d '/+=\n' >"$app/dev/.secrets/$f"
	chmod 600 "$app/dev/.secrets/$f"
done

# shellcheck source=dev/scripts/lib.sh
source "$app/dev/scripts/lib.sh"
dc up -d

echo "==> ERPNext $ERPNEXT_REF and gic_erp"
in_bench "bench set-config -g db_host mariadb \
	&& bench set-config -g redis_cache redis://redis-cache:6379 \
	&& bench set-config -g redis_queue redis://redis-queue:6379 \
	&& bench set-config -g redis_socketio redis://redis-queue:6379 \
	&& bench get-app --branch $ERPNEXT_REF erpnext \
	&& ./env/bin/pip install -q -e apps/gic_erp \
	&& (grep -qx gic_erp sites/apps.txt || echo gic_erp >> sites/apps.txt) \
	&& bench build --app gic_erp"

for site in gic-dev.local gic-test.local; do
	echo "==> site $site"
	in_bench "bench new-site $site \
		--db-root-password \"\$(cat /run/secrets/db_root_password)\" \
		--admin-password \"\$(cat /run/secrets/admin_password)\" \
		--mariadb-user-host-login-scope=% \
		--install-app erpnext --install-app gic_erp"
done
in_bench "bench --site gic-test.local set-config allow_tests true \
	&& bench --site gic-dev.local set-config developer_mode 1 \
	&& bench use gic-dev.local"

echo
echo "Done. Next:"
echo "  cd $app && pip install pre-commit && pre-commit install"
echo "  dev/scripts/up.sh      # http://localhost:8000, finish the setup wizard once"
echo "  dev/scripts/test.sh    # runs the suite on gic-test.local"
