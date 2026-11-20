#!/usr/bin/env bash
# Deploy a GICNEXT release to PRODUCTION from your laptop. Production is deliberately not
# in GitHub Actions: its SSH key never leaves this machine (GitHub only holds the staging key).
#
#   deploy/local-deploy.sh vX.Y.Z SERVER
#
# Env (optional):
#   GICNEXT_SSH_KEY      private key for the server   (default ~/.ssh/gicnext_prod)
#   GICNEXT_DEPLOY_USER  deploy user                  (default gicnext)
#   GICNEXT_REPO         GitHub repo with the release (default meerhamza00/gic-erp)
#
# Needs: gh (logged in), git, ssh, and the server's host key already in ~/.ssh/known_hosts
# (checked against the provider console, see docs/DEVOPS.md). Does what deploy.yml does for
# staging: download the release image, verify its sha256, upload through ssh-gate, deploy.
set -euo pipefail

tag="${1:?Usage: deploy/local-deploy.sh vX.Y.Z SERVER}"
host="${2:?Usage: deploy/local-deploy.sh vX.Y.Z SERVER}"
key="${GICNEXT_SSH_KEY:-$HOME/.ssh/gicnext_prod}"
user="${GICNEXT_DEPLOY_USER:-gicnext}"
gh_repo="${GICNEXT_REPO:-meerhamza00/gic-erp}"
here="$(cd "$(dirname "$0")/.." && pwd)"

[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Bad tag: $tag" >&2; exit 1; }
[[ "$host" =~ ^[A-Za-z0-9.:-]+$ ]] || { echo "Bad server name: $host" >&2; exit 1; }
[ -f "$key" ] || { echo "SSH key not found: $key (set GICNEXT_SSH_KEY)" >&2; exit 1; }
ssh-keygen -F "$host" >/dev/null || {
	echo "$host is not in ~/.ssh/known_hosts. Add its host key first (docs/DEVOPS.md, 'Pin the right host key')." >&2
	exit 1
}

version="${tag#v}"
file="gic-erp-$version-amd64.tar.zst"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "==> release files for $tag"
git -C "$here" fetch --quiet --tags origin
git -C "$here" rev-parse --verify --quiet "refs/tags/$tag" >/dev/null || { echo "Tag $tag not found." >&2; exit 1; }
git -C "$here" show "$tag:deploy/compose.yaml" >"$work/compose.yaml"
git -C "$here" show "$tag:deploy/server/remote-deploy.sh" >"$work/remote-deploy.sh"
gh release download "$tag" --repo "$gh_repo" --dir "$work" --pattern "$file" --pattern "$file.sha256"
if command -v sha256sum >/dev/null; then
	(cd "$work" && sha256sum --strict -c "$file.sha256")
else
	(cd "$work" && shasum -a 256 -c "$file.sha256")
fi

echo
read -r -p "Deploy $tag to PRODUCTION ($user@$host)? Type the tag again: " confirm
[ "$confirm" = "$tag" ] || { echo "Not confirmed. Nothing deployed."; exit 1; }

ssh_opts=(-i "$key" -o StrictHostKeyChecking=yes -o ServerAliveInterval=30 -o IdentitiesOnly=yes)
# shellcheck disable=SC2029,SC2094 # names expanded here on purpose (validated, ssh-gate re-checks); "$f" is only read
for f in "$file" "$file.sha256" compose.yaml remote-deploy.sh; do
	ssh "${ssh_opts[@]}" "$user@$host" "upload $f" <"$work/$f"
done
# shellcheck disable=SC2029 # $tag validated above
ssh "${ssh_opts[@]}" "$user@$host" "deploy $tag"
echo "Deployed $tag to production ($host)."
