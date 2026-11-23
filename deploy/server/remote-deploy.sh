#!/usr/bin/env bash
# Deploy one GICNEXT release on this server. Installed root-owned as
# /opt/gicnext/bin/remote-deploy.sh by bootstrap.sh. Called by ssh-gate ("deploy vX.Y.Z")
# from .github/workflows/deploy.yml, or by hand as root:
#   /opt/gicnext/bin/remote-deploy.sh v0.6.0
# It needs incoming/gic-erp-<version>-<arch>.tar.zst AND its .sha256 file.
#
# Steps: load image -> back up all sites -> switch image -> migrate -> health-check every
# site. If migration or a health check fails, it switches back to the previous image
# automatically and prints the backup taken just before, for a database restore if needed
# (migrations are forward-only).
set -euo pipefail

tag="${1:?Usage: remote-deploy.sh <tag, e.g. v0.6.0>}"
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || { echo "Bad tag: $tag" >&2; exit 1; }
version="${tag#v}"
root="${GICNEXT_ROOT:-/opt/gicnext}"
incoming="$root/incoming"
conf="$root/gicnext.conf"
keep_images="${GICNEXT_KEEP_IMAGES:-3}"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }
die() { log "ERROR: $*"; exit 1; }
compose() { docker compose --project-name "${GICNEXT_PROJECT:-gicnext}" --env-file "$conf" -f "$root/compose.yaml" "$@"; }
conf_get() { sed -n "s/^$1=//p" "$conf" | tail -1; }
conf_set() { sed -i.bak "s|^$1=.*|$1=$2|" "$conf" && rm -f "$conf.bak"; }

[ -f "$conf" ] || die "$conf not found. Run deploy/server/bootstrap.sh first."
[ -f "$root/compose.yaml" ] || die "$root/compose.yaml not found. Run deploy/server/bootstrap.sh first."

# Platform files are root-owned and change only through bootstrap.sh. If the release ships
# different ones, stop and ask for a bootstrap re-run instead of trusting uploaded copies.
if [ -f "$incoming/compose.yaml" ] && ! cmp -s "$incoming/compose.yaml" "$root/compose.yaml"; then
	die "this release changes deploy/compose.yaml: re-run deploy/server/bootstrap.sh as root with the $tag files first"
fi
self="$(readlink -f "$0")"
if [ -f "$incoming/remote-deploy.sh" ] && [ "$(readlink -f "$incoming/remote-deploy.sh")" != "$self" ] \
	&& ! cmp -s "$incoming/remote-deploy.sh" "$self"; then
	die "this release changes remote-deploy.sh: re-run deploy/server/bootstrap.sh as root with the $tag files first"
fi
rm -f "$incoming/compose.yaml" "$incoming/remote-deploy.sh"

tarball="$incoming/gic-erp-$version-amd64.tar.zst"
[ -f "$tarball" ] || tarball="$incoming/gic-erp-$version-arm64.tar.zst"
[ -f "$tarball" ] || die "image tarball for $version not found in $incoming"
[ -f "$tarball.sha256" ] || die "checksum file $tarball.sha256 missing: refusing to deploy"
(cd "$(dirname "$tarball")" && sha256sum --strict -c "$(basename "$tarball").sha256" >/dev/null) \
	|| die "checksum mismatch for $tarball"

log "loading image $version"
zstd -dc "$tarball" | docker load >/dev/null
docker image inspect "gicnext/gic-erp:$version" >/dev/null || die "tarball did not contain gicnext/gic-erp:$version"

previous="$(conf_get GICNEXT_VERSION)"

running="$(compose ps -q backend 2>/dev/null || true)"
if [ -n "$running" ]; then
	log "backing up all sites (previous version: ${previous:-none})"
	compose exec -T backend bench --site all backup >/dev/null || die "backup failed: nothing changed"
fi

SERVICES="backend frontend websocket queue-short queue-long scheduler"

# Every long-running service must be up and must not be restarting in a loop.
services_up() {
	local svc id state
	sleep "${GICNEXT_SETTLE_SECONDS:-20}"
	for svc in $SERVICES; do
		id="$(compose ps -q "$svc" 2>/dev/null || true)"
		state="$([ -n "$id" ] && docker inspect -f '{{.State.Running}} {{.RestartCount}}' "$id" 2>/dev/null || echo missing)"
		[ "$state" = "true 0" ] || { log "service not healthy: $svc ($state)"; return 1; }
	done
}

# Site names, read through the frontend (fails loudly if it cannot be listed).
sites() {
	# shellcheck disable=SC2016 # expanded inside the container, not here
	compose exec -T frontend bash -c \
		'for f in sites/*/site_config.json; do [ -e "$f" ] && basename "$(dirname "$f")"; done; true'
}

healthy() {
	local site ok list reply
	services_up || return 1
	list="$(sites)" || { log "cannot list sites"; return 1; }
	for site in $list; do
		ok=""
		for _ in $(seq 1 30); do
			reply="$(compose exec -T frontend curl -fsS -m 10 -H "Host: $site" http://127.0.0.1:8080/api/method/ping 2>/dev/null || true)"
			if [ "$reply" = '{"message":"pong"}' ]; then
				ok=1
				break
			fi
			sleep 2
		done
		[ -n "$ok" ] || { log "health check failed: $site"; return 1; }
		log "healthy: $site"
	done
}

start_version() {
	conf_set GICNEXT_VERSION "$1"
	compose up -d --remove-orphans
	local id state=""
	id="$(compose ps -aq migrator)"
	[ -n "$id" ] || { log "migrator did not start"; return 1; }
	for _ in $(seq 1 360); do # up to 30 minutes for big migrations
		state="$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$id")"
		[ "${state%% *}" = exited ] && break
		sleep 5
	done
	compose logs --no-log-prefix --tail 20 migrator || true
	[ "$state" = "exited 0" ] || { log "migration failed ($state)"; return 1; }
}

rollback() {
	log "ROLLING BACK to ${previous:-nothing}"
	if [ -z "$previous" ]; then
		compose down || true
		die "first deploy failed; stack stopped"
	fi
	conf_set GICNEXT_VERSION "$previous"
	# shellcheck disable=SC2086 # word-splitting the service list is intended
	compose up -d --remove-orphans --no-deps --force-recreate $SERVICES
	healthy || log "previous version is not healthy either: investigate now"
	log "latest backups (restore with: bench --site <site> restore <file>):"
	compose exec -T backend bash -c 'ls -t sites/*/private/backups/*-database.sql.gz 2>/dev/null | head -5' || true
	die "deploy of $version failed and was rolled back to $previous"
}

log "starting $version"
start_version "$version" || rollback
if list="$(sites 2>/dev/null)" && [ -z "$list" ]; then
	log "no sites yet: onboard the first client with onboard-client.sh (docs/DEVOPS.md, section 4)"
fi
healthy || rollback

log "pruning old images (keeping $keep_images)"
docker image ls gicnext/gic-erp --format '{{.Tag}}' \
	| grep -vxF -e "$version" -e "${previous:-__none__}" \
	| tail -n +"$((keep_images - 1))" \
	| xargs -r -I{} docker image rm "gicnext/gic-erp:{}" >/dev/null 2>&1 || true
rm -f "$tarball" "$tarball.sha256"

log "deployed $version (was ${previous:-none})"
