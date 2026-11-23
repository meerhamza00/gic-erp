#!/usr/bin/env bash
# Onboard a new GICNEXT client in one command (Milestone 6). Run as root on the server:
#
#   /opt/gicnext/bin/onboard-client.sh erp.acme.pk "Acme Cookware Pvt Ltd" "Foundry & Cookware"
#
# Options:
#   --fy-start-month N   first month of the fiscal year (default 7: July-June, Pakistan's tax year)
#   --resume             the site already exists (an earlier run stopped half way): finish it
#
# Steps:
#   1. check inputs (domain, company name, blueprint) and that the stack is running
#   2. bench new-site with ERPNext + gic_erp, with a generated Administrator password
#   3. ERPNext setup wizard for a Pakistani company, GIC Industry Profile, industry blueprint
#      (gic_erp.setup.onboarding.setup_client)
#   4. enable the scheduler
#   5. add the domain to SITES_RULE so Traefik serves it and gets a Let's Encrypt certificate
#   6. health check, then print the login once and save it root-only in credentials/
#
# Point the domain's DNS (A record) at this server before running it.
set -euo pipefail

root="${GICNEXT_ROOT:-/opt/gicnext}"
conf="$root/gicnext.conf"
project="${GICNEXT_PROJECT:-gicnext}"
# Keep in step with gic_erp/seed/blueprints.py (a unit test checks this list).
blueprints=("Foundry & Cookware" "Mandi & Wholesale Trader" "Importer & Exporter" "Sanitary Ware & Ceramics")

log() { echo "[onboard $(date -u +%H:%M:%S)] $*"; }
die() { echo "[onboard] ERROR: $*" >&2; exit 1; }
usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
compose() { docker compose --project-name "$project" --env-file "$conf" -f "$root/compose.yaml" "$@"; }
conf_get() { sed -n "s/^$1=//p" "$conf" | tail -1; }

# ------------------------------------------------------------------ 1. inputs
[ $# -ge 3 ] || usage
domain="$(tr '[:upper:]' '[:lower:]' <<<"$1")"
company="$2"
blueprint="$3"
shift 3
fy_start_month=7
resume=""
while [ $# -gt 0 ]; do
	case "$1" in
	--fy-start-month) fy_start_month="${2:-}"; shift 2 ;;
	--resume) resume=1; shift ;;
	*) usage ;;
	esac
done

domain_re='^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
company_re="^[[:alnum:]&.,'() _-]{2,100}\$"
[[ "$domain" =~ $domain_re ]] && [ ${#domain} -le 253 ] || die "not a valid domain: $domain"
[[ "$company" =~ $company_re ]] \
	|| die "company name must be 2 to 100 letters, digits, spaces or & . , ' ( ) -"
known=""
for b in "${blueprints[@]}"; do [ "$b" = "$blueprint" ] && known=1; done
[ -n "$known" ] || die "blueprint must be one of: $(printf '"%s" ' "${blueprints[@]}")"
[[ "$fy_start_month" =~ ^([1-9]|1[0-2])$ ]] || die "--fy-start-month must be 1 to 12"

[ -r "$conf" ] && [ -w "$conf" ] || die "cannot read and write $conf (run as root)"
[ -n "$(compose ps -q backend 2>/dev/null)" ] || die "the GICNEXT stack is not running: deploy a release first"
db_password="$(conf_get DB_PASSWORD)"
[ -n "$db_password" ] || die "DB_PASSWORD missing in $conf"

site_exists() { compose exec -T backend test -f "sites/$domain/site_config.json"; }

# ------------------------------------------------------------------ 2. site
admin_password=""
if site_exists; then
	[ -n "$resume" ] || die "site $domain already exists (use --resume to finish an earlier run)"
	log "site $domain exists: resuming"
else
	[ -z "$resume" ] || die "--resume given, but site $domain does not exist"
	admin_password="$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 20)"
	[ ${#admin_password} -eq 20 ] || die "could not generate a password"
	[ "${GITHUB_ACTIONS:-}" != true ] || echo "::add-mask::$admin_password" # keep it out of CI logs
	log "creating site $domain (ERPNext + gic_erp, a few minutes)"
	compose exec -T backend bench new-site "$domain" \
		--db-root-password "$db_password" --admin-password "$admin_password" \
		--mariadb-user-host-login-scope=% --install-app erpnext --install-app gic_erp >/dev/null \
		|| die "bench new-site failed. Fix the cause, then drop the half-made site with:
  docker compose --project-name $project --env-file $conf -f $root/compose.yaml exec backend \\
    bench drop-site $domain --db-root-password \"\$DB_PASSWORD\" --no-backup"
fi

on_error() {
	echo "[onboard] Stopped. The site exists; after fixing the cause run again with --resume." >&2
}
trap on_error ERR

# ------------------------------------------------------------------ 3. company + blueprint
log "setting up $company ($blueprint)"
summary="$(compose exec -T \
	-e GIC_ONBOARD_COMPANY="$company" \
	-e GIC_ONBOARD_BLUEPRINT="$blueprint" \
	-e GIC_ONBOARD_FY_START_MONTH="$fy_start_month" \
	backend bench --site "$domain" execute gic_erp.setup.onboarding.setup_client_from_env)"
echo "$summary"

# ------------------------------------------------------------------ 4. scheduler
compose exec -T backend bench --site "$domain" enable-scheduler >/dev/null
log "scheduler enabled"

# ------------------------------------------------------------------ 5. Traefik host rule
rule="$(conf_get SITES_RULE)"
host_rule="Host(\`$domain\`)"
if [[ "$rule" == *"$host_rule"* ]]; then
	log "$domain already in SITES_RULE"
else
	# shellcheck disable=SC2016 # literal backticks: the placeholder rule from gicnext.conf.example
	if [ -z "$rule" ] || [ "$rule" = 'Host(`erp.example.com`)' ]; then
		new_rule="$host_rule"
	else
		new_rule="$rule || $host_rule"
	fi
	tmp="$(mktemp "$conf.XXXXXX")"
	if grep -q '^SITES_RULE=' "$conf"; then
		awk -v r="$new_rule" 'BEGIN{done=0} /^SITES_RULE=/{ if(!done){print "SITES_RULE=" r; done=1}; next } {print}' "$conf" >"$tmp"
	else
		cat "$conf" >"$tmp" && echo "SITES_RULE=$new_rule" >>"$tmp"
	fi
	chmod --reference="$conf" "$tmp" 2>/dev/null || chmod 600 "$tmp"
	mv "$tmp" "$conf"
	compose up -d --no-deps frontend >/dev/null 2>&1
	log "added $domain to SITES_RULE (Traefik requests the certificate on the first visit)"
fi

# ------------------------------------------------------------------ 6. check and hand over
ok=""
for _ in $(seq 1 30); do
	reply="$(compose exec -T frontend curl -fsS -m 10 -H "Host: $domain" http://127.0.0.1:8080/api/method/ping 2>/dev/null || true)"
	if [ "$reply" = '{"message":"pong"}' ]; then ok=1; break; fi
	sleep 2
done
[ -n "$ok" ] || die "$domain does not answer /api/method/ping"
trap - ERR

if [ -n "$admin_password" ]; then
	install -d -m 700 "$root/credentials"
	(umask 077 && printf 'site=%s\nuser=Administrator\npassword=%s\ncreated=%s\n' \
		"$domain" "$admin_password" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$root/credentials/$domain")
fi

echo
echo "Client ready: https://$domain"
echo "  Company:   $company"
echo "  Blueprint: $blueprint"
if [ -n "$admin_password" ]; then
	echo "  Login:     Administrator / $admin_password"
	echo "  (shown once; also saved root-only in $root/credentials/$domain)"
	echo "  Ask the client to change it at first login and to create named users."
else
	echo "  Login:     unchanged (resumed run)"
fi
