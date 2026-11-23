#!/usr/bin/env bash
# CI: rehearse real deploys of a freshly built image on the runner, with the same
# remote-deploy.sh that production uses (Traefik off, everything else identical).
#
#   1. first deploy on an empty server        -> stack comes up
#   2. onboard a client with onboard-client.sh -> ping, login page, assets, blueprint,
#      SITES_RULE, saved credentials; re-run refused, --resume creates nothing new
#   3. redeploy over a live site              -> backup + migrate + health check
#   4. deploy a deliberately broken release   -> must fail and roll back automatically
#   5. refusals: no .sha256, bad checksum, changed compose.yaml -> must not deploy
#
# Like on a server set up by bootstrap.sh, compose.yaml sits in $GICNEXT_ROOT (not taken
# from incoming/) and remote-deploy.sh runs from its own path.
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
# Upload what deploy.yml uploads: the image, its .sha256 and the release's compose.yaml.
stage() {
	local file="gic-erp-$2-amd64.tar.zst"
	cp "$1" "$root/incoming/$file"
	(cd "$root/incoming" && sha256sum "$file" >"$file.sha256")
	cp "$repo/deploy/compose.yaml" "$root/incoming/"
}
deploy() { bash "$repo/deploy/server/remote-deploy.sh" "$@"; }
must_refuse() {
	local why="$1"
	shift
	if deploy "$@"; then
		echo "Deploy should have been refused: $why" >&2
		exit 1
	fi
	echo "ok: refused ($why)"
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
cp "$repo/deploy/compose.yaml" "$root/compose.yaml"
db_password="$(openssl rand -hex 24)"
echo "::add-mask::$db_password"
sed -e "s|^DB_PASSWORD=.*|DB_PASSWORD=$db_password|" -e "s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES=|" \
	"$repo/deploy/server/gicnext.conf.example" >"$root/gicnext.conf"

step "1. first deploy on an empty server"
stage "$tarball" "$version"
deploy "v$version"
end

step "2. onboard a client site with onboard-client.sh and check it"
onboard() { bash "$repo/deploy/server/onboard-client.sh" "$@"; }
onboard "$site" "GIC Smoke Foundry" "Foundry & Cookware"
expect /api/method/ping pong
expect /login GICNEXT
fetch /assets/gic_erp/images/gicnext-logo.png >/dev/null && echo "ok: logo asset served"
apps="$(compose exec -T backend bench --site "$site" list-apps)"
grep -q gic_erp <<<"$apps" && echo "ok: gic_erp installed"
item="$(compose exec -T backend bench --site "$site" execute frappe.db.get_value --args '["Item", "Non-Stick Karahi 28cm", "item_code"]')"
grep -q "Non-Stick Karahi" <<<"$item" && echo "ok: blueprint loaded"
grep -q "SITES_RULE=Host(\`$site\`)" "$root/gicnext.conf" && echo "ok: site added to SITES_RULE"
[ "$(stat -c %a "$root/credentials/$site" 2>/dev/null || stat -f %Lp "$root/credentials/$site")" = 600 ] \
	&& echo "ok: credentials saved root-only"
if onboard "$site" "GIC Smoke Foundry" "Foundry & Cookware" 2>/dev/null; then
	echo "Onboarding an existing site without --resume should be refused" >&2
	exit 1
fi
echo "ok: refused to onboard an existing site"
rerun="$(onboard "$site" "GIC Smoke Foundry" "Foundry & Cookware" --resume)"
grep -q '"created": 0' <<<"$rerun" && echo "ok: --resume re-run creates nothing new"
end

step "3. redeploy over a live site (backup, migrate, health)"
stage "$tarball" "$version"
deploy "v$version"
compose exec -T backend bash -c "ls sites/$site/private/backups/*-database.sql.gz" >/dev/null && echo "ok: pre-deploy backup exists"
end

step "4. broken release must roll back"
broken=0.0.0-broken
printf 'FROM gicnext/gic-erp:%s\nCMD ["false"]\n' "$version" | docker build -q -t "gicnext/gic-erp:$broken" - >/dev/null
docker save "gicnext/gic-erp:$broken" | zstd -1 -q -T0 >"$tmp/broken.tar.zst"
stage "$tmp/broken.tar.zst" "$broken"
if deploy "v$broken"; then
	echo "Broken release was reported as deployed" >&2
	exit 1
fi
grep -qx "GICNEXT_VERSION=$version" "$root/gicnext.conf"
expect /api/method/ping pong
echo "rolled back to $version and healthy"
end

step "5. deploys that must be refused (nothing changes)"
file="gic-erp-$version-amd64.tar.zst"
stage "$tarball" "$version"
rm "$root/incoming/$file.sha256"
must_refuse "missing .sha256" "v$version"
stage "$tarball" "$version"
echo "0000000000000000000000000000000000000000000000000000000000000000  $file" >"$root/incoming/$file.sha256"
must_refuse "checksum mismatch" "v$version"
stage "$tarball" "$version"
echo "# changed by a release" >>"$root/incoming/compose.yaml"
must_refuse "compose.yaml changed without bootstrap" "v$version"
grep -qx "GICNEXT_VERSION=$version" "$root/gicnext.conf"
expect /api/method/ping pong
end
