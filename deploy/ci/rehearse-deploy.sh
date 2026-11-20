#!/usr/bin/env bash
# CI: rehearse real deploys of a freshly built image on the runner, with the same
# remote-deploy.sh that production uses (Traefik off, everything else identical).
#
#   1. first deploy on an empty server        -> stack comes up
#   2. create a client site (ERPNext + gic_erp) -> ping, GICNEXT login page, assets
#   3. redeploy over a live site              -> backup + migrate + health check
#   4. deploy a deliberately broken release   -> must fail and roll back automatically
#
# Usage: deploy/ci/rehearse-deploy.sh <version> <image-tarball.tar.zst>
set -euo pipefail

version="${1:?version}"
tarball="$(cd "$(dirname "${2:?tarball}")" && pwd)/$(basename "$2")"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
export GICNEXT_ROOT="$tmp/gicnext-rehearsal"
export GICNEXT_PROJECT=gicnext-ci
site=smoke.localhost
root="$GICNEXT_ROOT"

compose() { docker compose --project-name "$GICNEXT_PROJECT" --env-file "$root/gicnext.conf" -f "$root/compose.yaml" "$@"; }
step() { echo; echo "::group::$*"; }
end() { echo "::endgroup::"; }
fetch() { compose exec -T frontend curl -fsS -m 20 -H "Host: $site" "http://127.0.0.1:8080$1"; }
# Capture first, then match: "curl | grep -q" can fail under pipefail (SIGPIPE on big pages).
expect() {
	local body
	body="$(fetch "$1")" || { echo "GET $1 failed" >&2; return 1; }
	grep -q -- "$2" <<<"$body" || { echo "GET $1: '$2' not found" >&2; return 1; }
	echo "ok: GET $1 contains '$2'"
}
stage() {
	cp "$repo/deploy/compose.yaml" "$repo/deploy/server/remote-deploy.sh" "$root/incoming/"
	cp "$1" "$root/incoming/gic-erp-$2-amd64.tar.zst"
}

cleanup() {
	if [ "${keep:-}" != 1 ]; then compose down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
on_exit() {
	local status=$?
	[ "$status" -eq 0 ] || compose logs --tail 60 >&2 || true
	cleanup
}
trap on_exit EXIT

rm -rf "$root" && mkdir -p "$root/incoming"
db_password="$(openssl rand -hex 24)"
echo "::add-mask::$db_password"
sed -e "s|^DB_PASSWORD=.*|DB_PASSWORD=$db_password|" -e "s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES=|" \
	"$repo/deploy/server/gicnext.conf.example" >"$root/gicnext.conf"

step "1. first deploy on an empty server"
stage "$tarball" "$version"
bash "$root/incoming/remote-deploy.sh" "v$version"
end

step "2. create site $site and check it"
admin_password="$(openssl rand -hex 16)"
echo "::add-mask::$admin_password"
compose exec -T backend bench new-site "$site" \
	--db-root-password "$db_password" --admin-password "$admin_password" \
	--mariadb-user-host-login-scope=% --install-app erpnext --install-app gic_erp
expect /api/method/ping pong
expect /login GICNEXT
fetch /assets/gic_erp/images/gicnext-logo.png >/dev/null && echo "ok: logo asset served"
apps="$(compose exec -T backend bench --site "$site" list-apps)"
grep -q gic_erp <<<"$apps" && echo "ok: gic_erp installed"
end

step "3. redeploy over a live site (backup, migrate, health)"
stage "$tarball" "$version"
bash "$root/incoming/remote-deploy.sh" "v$version"
compose exec -T backend bash -c "ls sites/$site/private/backups/*-database.sql.gz" >/dev/null && echo "ok: pre-deploy backup exists"
end

step "4. broken release must roll back"
broken=0.0.0-broken
printf 'FROM gicnext/gic-erp:%s\nCMD ["false"]\n' "$version" | docker build -q -t "gicnext/gic-erp:$broken" - >/dev/null
docker save "gicnext/gic-erp:$broken" | zstd -1 -q -T0 >"$tmp/broken.tar.zst"
stage "$tmp/broken.tar.zst" "$broken"
if bash "$root/incoming/remote-deploy.sh" "v$broken"; then
	echo "Broken release was reported as deployed" >&2
	exit 1
fi
grep -qx "GICNEXT_VERSION=$version" "$root/gicnext.conf"
expect /api/method/ping pong
echo "rolled back to $version and healthy"
end
