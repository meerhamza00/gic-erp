#!/usr/bin/env bash
# Setup of an Ubuntu 22.04 / 24.04 server for GICNEXT, and update of its platform files.
# Run as root, with deploy/compose.yaml copied next to the deploy/server files:
#
#   ssh root@SERVER mkdir -p /root/gicnext-platform
#   scp deploy/server/* deploy/compose.yaml root@SERVER:/root/gicnext-platform/
#   ssh root@SERVER 'bash /root/gicnext-platform/bootstrap.sh "ssh-ed25519 AAAA... github-deploy"'
#
# Installs Docker (Ubuntu packages), zstd, ufw, fail2ban and unattended security upgrades;
# opens only SSH, 80 and 443; creates /opt/gicnext with a root-only gicnext.conf holding a
# random DB password.
#
# The "gicnext" deploy user is NOT in the docker group (docker group = root). Its key is
# locked to /opt/gicnext/bin/ssh-gate, which can only upload files into incoming/ and run
# the root-owned /opt/gicnext/bin/remote-deploy.sh through one sudoers entry. compose.yaml
# and remote-deploy.sh are root-owned and change only when this script runs again, so a
# stolen deploy key cannot replace them.
#
# Safe to run again; re-run it whenever a release changes deploy/compose.yaml or
# deploy/server/*.sh (the deploy refuses until you do). It never changes the SSH daemon
# config (no lock-out risk).
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

for f in gicnext.conf.example compose.yaml remote-deploy.sh ssh-gate.sh; do
	[ -f "$here/$f" ] || { echo "$f must sit next to this script (see the header)." >&2; exit 1; }
done
case "$pubkey" in
ssh-ed25519\ * | ssh-rsa\ * | ecdsa-sha2-*) ;;
*) echo "That does not look like a public key: $pubkey" >&2; exit 1 ;;
esac
key_type_and_body="$(awk '{print $1" "$2}' <<<"$pubkey")"

echo "==> deploy user (no docker group, key locked to ssh-gate)"
id "$user" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$user"
if id -nG "$user" | tr ' ' '\n' | grep -qx docker; then gpasswd -d "$user" docker >/dev/null; fi
install -d -m 700 -o "$user" -g "$user" "/home/$user/.ssh"
keys="/home/$user/.ssh/authorized_keys"
touch "$keys"
# Drop any earlier line for this key (e.g. an unrestricted one), then add the locked line.
grep -vF "$key_type_and_body" "$keys" >"$keys.new" || true
echo "restrict,command=\"$root/bin/ssh-gate\" $pubkey" >>"$keys.new"
mv "$keys.new" "$keys"
chown "$user:$user" "$keys"
chmod 600 "$keys"

echo "==> $root (platform files root-owned)"
install -d -m 755 -o root -g root "$root" "$root/bin"
install -d -m 750 -o "$user" -g "$user" "$root/incoming"
install -m 755 -o root -g root "$here/ssh-gate.sh" "$root/bin/ssh-gate"
install -m 755 -o root -g root "$here/remote-deploy.sh" "$root/bin/remote-deploy.sh"
install -m 644 -o root -g root "$here/compose.yaml" "$root/compose.yaml"
rm -f "$root/compose.yaml.prev"
if [ ! -f "$root/gicnext.conf" ]; then
	password="$(openssl rand -base64 32 | tr -d '/+=\n')"
	(umask 077 && sed "s|^DB_PASSWORD=.*|DB_PASSWORD=$password|" "$here/gicnext.conf.example" >"$root/gicnext.conf")
	echo "    created $root/gicnext.conf (random DB password). Edit LETSENCRYPT_EMAIL and SITES_RULE."
fi
chown root:root "$root/gicnext.conf"
chmod 600 "$root/gicnext.conf"

echo "==> sudoers: $user may run only $root/bin/remote-deploy.sh as root"
sudoers=/etc/sudoers.d/gicnext-deploy
printf '%s ALL=(root) NOPASSWD: %s/bin/remote-deploy.sh\n' "$user" "$root" >"$sudoers.tmp"
chmod 440 "$sudoers.tmp"
visudo -cf "$sudoers.tmp" >/dev/null || { rm -f "$sudoers.tmp"; echo "sudoers check failed" >&2; exit 1; }
mv "$sudoers.tmp" "$sudoers"

echo "==> firewall: SSH, HTTP, HTTPS only"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo
echo "Done. Next:"
echo "  1. As root, edit $root/gicnext.conf (LETSENCRYPT_EMAIL, SITES_RULE); point DNS at this server."
echo "  2. Add the GitHub secrets listed in docs/DEVOPS.md, then run the Deploy workflow."
