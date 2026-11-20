#!/usr/bin/env bash
# One-time setup of an Ubuntu 22.04 / 24.04 server for GICNEXT. Run as root:
#
#   scp deploy/server/bootstrap.sh deploy/server/gicnext.conf.example root@SERVER:/root/
#   ssh root@SERVER 'bash /root/bootstrap.sh "ssh-ed25519 AAAA... github-deploy"'
#
# Installs Docker (Ubuntu packages), zstd, ufw, fail2ban and unattended security upgrades;
# creates the non-root "gicnext" deploy user with the given public key; opens only SSH,
# 80 and 443; creates /opt/gicnext with a gicnext.conf holding a random DB password.
# Safe to run again. It never changes the SSH daemon config (no lock-out risk).
set -euo pipefail

pubkey="${1:?Usage: bootstrap.sh \"<deploy public key>\"}"
here="$(cd "$(dirname "$0")" && pwd)"
root=/opt/gicnext
user=gicnext

[ "$(id -u)" = 0 ] || { echo "Run as root." >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release
[ "${ID:-}" = ubuntu ] || echo "Warning: tested on Ubuntu only (found ${ID:-unknown})." >&2

echo "==> packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 zstd curl ufw fail2ban unattended-upgrades
systemctl enable --now docker fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> deploy user"
id "$user" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$user"
usermod -aG docker "$user"
install -d -m 700 -o "$user" -g "$user" "/home/$user/.ssh"
touch "/home/$user/.ssh/authorized_keys"
grep -qxF "$pubkey" "/home/$user/.ssh/authorized_keys" || echo "$pubkey" >>"/home/$user/.ssh/authorized_keys"
chown "$user:$user" "/home/$user/.ssh/authorized_keys"
chmod 600 "/home/$user/.ssh/authorized_keys"

echo "==> $root"
install -d -m 750 -o "$user" -g "$user" "$root" "$root/incoming"
if [ ! -f "$root/gicnext.conf" ]; then
	template="$here/gicnext.conf.example"
	[ -f "$template" ] || { echo "gicnext.conf.example must sit next to this script." >&2; exit 1; }
	password="$(openssl rand -base64 32 | tr -d '/+=\n')"
	sed "s|^DB_PASSWORD=.*|DB_PASSWORD=$password|" "$template" >"$root/gicnext.conf"
	chown "$user:$user" "$root/gicnext.conf"
	chmod 600 "$root/gicnext.conf"
	echo "    created $root/gicnext.conf (random DB password). Edit LETSENCRYPT_EMAIL and SITES_RULE."
fi

echo "==> firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo
echo "Done. Next:"
echo "  1. Edit $root/gicnext.conf (LETSENCRYPT_EMAIL, SITES_RULE); point DNS at this server."
echo "  2. Add the GitHub secrets listed in docs/DEVOPS.md, then run the Deploy workflow."
