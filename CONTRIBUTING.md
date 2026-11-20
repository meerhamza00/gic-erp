# Contributing to GICNEXT

1. Branch from `main`: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
2. Install the hooks once: `pip install pre-commit && pre-commit install`.
3. Write the test with the change. Run `./scripts/test.sh` from the workspace root.
4. Commit with [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`,
   `fix(fbr): …`, `docs: …`. The commit-msg hook checks this.
5. Open a PR. Its title must also be a Conventional Commit, because PRs are squash merged
   and the title becomes the commit release-please reads for the version and CHANGELOG.
6. CI must be green: lint, PR title, security (gitleaks, bandit) and the Frappe tests.

Rules:

- No secrets in code, fixtures or tests. Use Frappe Password fields, server config or
  GitHub Actions secrets.
- Every whitelisted method checks permissions and validates its input.
- Every feature has a happy path, error states and loading states, and a test.
- Frappe/ERPNext versions change only through `deploy/versions.conf`.

How releases and deploys work: [docs/DEVOPS.md](docs/DEVOPS.md).
