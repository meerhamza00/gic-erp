# Security policy

## Reporting a vulnerability

Do not open a public issue. Email the maintainer (see the GitHub profile of the repository
owner) with the steps to reproduce, the affected version and the impact. You will get a
reply within 5 working days.

## Supported versions

Only the latest release receives fixes.

## How this project handles security

- Secrets live only in GitHub Actions secrets, Frappe Password fields and a `chmod 600`
  config file on each server. gitleaks checks every commit locally and the whole history in CI.
- bandit checks the Python code in CI. Grype scans every release image and the report is
  attached to the release.
- Every GitHub Action is pinned to a full commit SHA, the default workflow token is
  read-only, and Dependabot proposes updates every week.
- Servers: non-root deploy user, SSH keys only for deploys, pinned host keys, firewall
  allowing only SSH, 80 and 443, fail2ban, automatic security updates, HTTPS via Let's Encrypt.
- Every deploy backs up all sites first and rolls back automatically if migration or a
  health check fails.
