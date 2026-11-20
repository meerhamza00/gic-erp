# GICNEXT DevOps runbook

How code gets from a laptop to a client server. The reasons behind each choice are in
[ADR 0001](adr/0001-devops-platform.md). Everything here is free and open source.

```
laptop ──pre-commit──> branch ──PR (CI)──> main ──release PR──> vX.Y.Z
                                                                   │
                                     image.yml: build → rehearse deploy + rollback → scan → attach to Release
                                                                   │
                                     deploy.yml: staging (automatic) · production: deploy/local-deploy.sh from the laptop
```

## 1. Daily work

```bash
git switch -c feat/short-name          # never commit on main
# ... code ...
./scripts/test.sh                       # from the workspace root: gic_erp tests on gic-test.local
git commit -m "feat: what changed"      # hooks: ruff, prettier, eslint, gitleaks, shellcheck, ...
git push -u origin feat/short-name      # a pre-push hook blocks pushes straight to main
gh pr create --fill                     # the PR title must be a Conventional Commit
```

One-time setup per clone: `pip install pre-commit && pre-commit install`.

| Commit type | Effect on the next version (while below 1.0) |
|---|---|
| `fix:` | patch (0.5.0 → 0.5.1) |
| `feat:` | minor (0.5.0 → 0.6.0) |
| `feat!:` or a `BREAKING CHANGE:` footer | minor below 1.0, major from 1.0 |
| `docs:` `chore:` `ci:` `build:` `refactor:` `test:` | no release on their own |

PRs are **squash merged**, so the PR title is the commit that release-please reads.

### What CI checks on every PR (`.github/workflows/ci.yml`)

| Job | Checks |
|---|---|
| lint | every pre-commit hook on every file |
| pr-title | Conventional Commit format |
| security | gitleaks over the full git history; bandit |
| tests | a real bench (pinned Frappe + ERPNext, MariaDB, Redis), a fresh site, `run-tests --app gic_erp`, `bench build --app gic_erp` |

PRs that touch `deploy/` also run `image.yml` (build, deploy rehearsal, scan) without publishing.

## 2. Releasing

1. Merge PRs into `main`. release-please keeps a PR called **"chore(main): release x.y.z"**
   open, with the version bump and the CHANGELOG.
2. When you want to ship, merge that PR. That creates the tag and the GitHub Release.
3. `image.yml` then builds the image from the tag and runs the deploy rehearsal: first
   deploy, a site, redeploy, and a broken release that must roll back. It scans the image
   with Grype and attaches `gic-erp-X.Y.Z-amd64.tar.zst`, its `.sha256` and the scan report
   to the release.
4. If staging secrets exist, `deploy.yml` deploys that release to staging.
5. **Production, from your laptop** (production is not in GitHub Actions, so its key never
   sits in GitHub):
   ```bash
   deploy/local-deploy.sh vX.Y.Z PROD_SERVER
   ```
   It downloads the release image, checks its sha256, asks you to type the tag again, then
   uploads and deploys through the server's ssh-gate. Key: `~/.ssh/gicnext_prod`
   (or set `GICNEXT_SSH_KEY`).

If a release's image failed to attach: Actions → Image → Run workflow with its tag. An image
that is already attached is never replaced; ship a fix as a new release.

## 3. Setting up a server (once per server)

Any Ubuntu 22.04/24.04 VPS with 2 vCPU, 4 GB RAM and 40 GB disk is enough for several
small sites. Point each client's DNS name (A record) at it first.

```bash
# On the laptop: one key pair per server.
#   staging:    used by GitHub Actions, no passphrase   -> ~/.ssh/gicnext_deploy
#   production: stays on the laptop, WITH a passphrase  -> ~/.ssh/gicnext_prod
ssh-keygen -t ed25519 -N "" -C github-deploy -f ~/.ssh/gicnext_deploy   # staging
ssh-keygen -t ed25519 -C gicnext-prod -f ~/.ssh/gicnext_prod           # production

ssh root@SERVER mkdir -p /root/gicnext-platform
scp deploy/server/* deploy/compose.yaml root@SERVER:/root/gicnext-platform/
ssh root@SERVER "bash /root/gicnext-platform/bootstrap.sh '$(cat ~/.ssh/gicnext_deploy.pub)'"
# (on the production server, pass ~/.ssh/gicnext_prod.pub instead)
```

Then, as root, edit `/opt/gicnext/gicnext.conf` and set `LETSENCRYPT_EMAIL` and
`SITES_RULE`. Leave `DB_PASSWORD` as generated. The file is root-only (`chmod 600`).

**What the deploy key can do.** The key is locked to `/opt/gicnext/bin/ssh-gate`: it can
upload release files into `incoming/` and start `/opt/gicnext/bin/remote-deploy.sh vX.Y.Z`,
nothing else (no shell, no scp, no forwarding). The `gicnext` user is not in the docker
group; one sudoers entry lets it run only that root-owned deploy script. `compose.yaml` and
the deploy scripts are root-owned and change only when you run `bootstrap.sh` again.

**When a release changes `deploy/compose.yaml` or `deploy/server/*.sh`**, the deploy stops
with "re-run bootstrap.sh". Check out that tag, repeat the `scp` and `bootstrap.sh` lines
above (same public key), then run the deploy again.

**Pin the right host key.** Get the key with `ssh-keyscan -t ed25519 SERVER`, then compare
its fingerprint (`ssh-keyscan -t ed25519 SERVER | ssh-keygen -lf -`) with the one in your
VPS provider's console before saving it as a secret. A mismatch means someone is in the
middle: stop.

### GitHub secrets

Staging only. Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `STAGING_DEPLOY_HOST` | staging server IP or hostname |
| `STAGING_DEPLOY_USER` | `gicnext` (optional, that is the default) |
| `STAGING_SSH_KEY` | contents of `~/.ssh/gicnext_deploy` (the private key) |
| `STAGING_KNOWN_HOSTS` | output of `ssh-keyscan -t ed25519 SERVER`, fingerprint checked as above |

Without these secrets, staging deploys are skipped with a notice. Nothing fails.
**Never add production secrets to GitHub.** Any repo collaborator's workflow could read
them, and a private repo on GitHub Free has no approval gate to stop it.

For production, add the server's host key to the laptop's `~/.ssh/known_hosts` (fingerprint
checked as above). `local-deploy.sh` refuses a server that is not there.

First deploy: staging via Actions → Deploy → Run workflow with the latest tag; production
with `deploy/local-deploy.sh vX.Y.Z PROD_SERVER`.

## 4. First site and new client sites

On the server, as root (`sudo -i`; the `gicnext` user has no docker access):

```bash
cd /opt/gicnext
dc() { docker compose --project-name gicnext --env-file gicnext.conf -f compose.yaml "$@"; }
set -a; . ./gicnext.conf; set +a

dc exec backend bench new-site erp.client.pk \
  --db-root-password "$DB_PASSWORD" --admin-password 'choose-a-strong-one' \
  --mariadb-user-host-login-scope=% --install-app erpnext --install-app gic_erp
```

Add the site to `SITES_RULE` in `gicnext.conf`, for example
``SITES_RULE=Host(`erp.client.pk`) || Host(`erp.other.pk`)``, then apply it with
`dc up -d frontend`. Traefik gets the Let's Encrypt certificate on the first request.

## 5. What a deploy does (`deploy/server/remote-deploy.sh`)

1. Refuses if the release ships a different `compose.yaml` or `remote-deploy.sh` than the
   root-owned ones (re-run `bootstrap.sh`), or if the `.sha256` file is missing or wrong.
   Then loads the image.
2. Backs up every site (`bench --site all backup`). If that fails, nothing is changed.
3. Switches `GICNEXT_VERSION` and starts the new containers.
4. Runs migrations (`bench --site all migrate`, up to 30 minutes).
5. Health check: every service is running and not restarting, and every site answers `/api/method/ping`.
6. If 4 or 5 fails, it **switches back to the previous image** automatically and prints
   the backups taken in step 2.
7. Keeps the last 3 images and deletes older ones.

## 6. Rollback and restore

**Image rollback** (code only, any time): deploy the previous tag again, with
`deploy/local-deploy.sh vPREVIOUS PROD_SERVER` (staging: Actions → Deploy). Its image is still on the server (the last 3 are kept) or comes from its Release.

**Database restore** (needed only if a migration ran and you go back to an older
version, because migrations are forward-only):

```bash
dc exec backend bash -c 'ls -t sites/erp.client.pk/private/backups/ | head'
dc exec backend bench --site erp.client.pk restore \
  sites/erp.client.pk/private/backups/<timestamp>-erp_client_pk-database.sql.gz \
  --db-root-password "$DB_PASSWORD"
dc exec backend bench --site erp.client.pk migrate
```

**Backups:** Ofelia runs `bench --site all backup` every 6 hours (`BACKUP_CRONSTRING`).
They stay on the server. Copy them off the server too, for example a nightly
`rsync` or `rclone` of the `gicnext_sites` volume to free cloud storage. A backup that
exists only on the same disk does not protect against losing the server.

## 7. Upgrading Frappe / ERPNext

1. Edit `deploy/versions.conf` (both refs and both images) on a branch.
2. Open a PR (`build: bump ERPNext to v15.x`). CI runs the tests on the new versions and
   `image.yml` runs the full deploy rehearsal.
3. Merge, then release as usual.

Dependabot opens PRs every week for GitHub Actions and the infrastructure images
(Traefik, MariaDB patch versions, Redis, Ofelia).

## 8. arm64 servers (e.g. Oracle Cloud free Ampere)

Images are built for amd64, because arm64 runners are not free for private repos. On an
arm64 server, build the image there from the release tag, then deploy it the same way:

```bash
git clone --branch vX.Y.Z --depth 1 https://github.com/meerhamza00/gic-erp.git /tmp/gic-erp
cd /tmp/gic-erp && set -a && . deploy/versions.conf && set +a
docker build -f deploy/Containerfile -t gicnext/gic-erp:X.Y.Z \
  --build-arg FRAPPE_BUILD_IMAGE="$FRAPPE_BUILD_IMAGE" --build-arg FRAPPE_BASE_IMAGE="$FRAPPE_BASE_IMAGE" \
  --build-arg FRAPPE_REF="$FRAPPE_REF" --build-arg ERPNEXT_REF="$ERPNEXT_REF" --build-arg GICNEXT_VERSION=X.Y.Z .
docker save gicnext/gic-erp:X.Y.Z | zstd -o /opt/gicnext/incoming/gic-erp-X.Y.Z-arm64.tar.zst
(cd /opt/gicnext/incoming && sha256sum gic-erp-X.Y.Z-arm64.tar.zst > gic-erp-X.Y.Z-arm64.tar.zst.sha256)
cp deploy/compose.yaml /opt/gicnext/incoming/
/opt/gicnext/bin/remote-deploy.sh vX.Y.Z   # as root
```

## 9. Local development

From the workspace root (`ERP - GIC/`): `./scripts/dev-up.sh` starts the dev stack
(defined in `dev/compose.yaml` in this repo) at http://localhost:8000, and
`./scripts/test.sh` runs the tests. On a new laptop, `dev/scripts/bootstrap.sh` builds the
whole workspace from scratch.
