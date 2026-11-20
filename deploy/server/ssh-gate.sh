#!/usr/bin/env bash
# Forced command for the GitHub deploy key (installed by bootstrap.sh as
# /opt/gicnext/bin/ssh-gate, root-owned). The key's authorized_keys line is
#   restrict,command="/opt/gicnext/bin/ssh-gate" ssh-ed25519 AAAA... github-deploy
# so the key can do exactly two things, whatever the client asks for:
#
#   ssh gicnext@SERVER "upload <file>" < file   write one allowed file into incoming/
#   ssh gicnext@SERVER "deploy vX.Y.Z"          run the root-owned remote-deploy.sh
#
# No shell, no port forwarding, no scp/sftp. The deploy user is not in the docker group;
# only /opt/gicnext/bin/remote-deploy.sh runs as root (via one sudoers entry).
set -euo pipefail

incoming=/opt/gicnext/incoming
max_bytes=$((4 * 1024 * 1024 * 1024))
tag_re='^v[0-9]+\.[0-9]+\.[0-9]+$'
file_re='^(gic-erp-[0-9]+\.[0-9]+\.[0-9]+-(amd64|arm64)\.tar\.zst(\.sha256)?|compose\.yaml|remote-deploy\.sh)$'

deny() {
	echo "ssh-gate: refused ($1)" >&2
	logger -t gicnext-ssh-gate "refused: $1" 2>/dev/null || true
	exit 1
}

cmd="${SSH_ORIGINAL_COMMAND:-}"
[ -n "$cmd" ] || deny "interactive login"
[[ "$cmd" =~ ^[A-Za-z0-9.\ _-]+$ ]] || deny "unexpected characters"
read -r verb arg extra <<<"$cmd"
[ -z "${extra:-}" ] || deny "too many arguments"

case "$verb" in
upload)
	[[ "${arg:-}" =~ $file_re ]] || deny "file name not allowed"
	tmp="$(mktemp "$incoming/.upload.XXXXXX")"
	trap 'rm -f "$tmp"' EXIT
	head -c "$max_bytes" >"$tmp"
	chmod 640 "$tmp"
	mv -f "$tmp" "$incoming/$arg"
	trap - EXIT
	echo "uploaded $arg"
	;;
deploy)
	[[ "${arg:-}" =~ $tag_re ]] || deny "bad tag"
	exec sudo -n /opt/gicnext/bin/remote-deploy.sh "$arg"
	;;
*)
	deny "unknown command"
	;;
esac
