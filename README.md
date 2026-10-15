# CSE 4316 — Raytheon Senior Design

## Working on the project

1. Create a branch from `main`.
2. Commit your changes and open a pull request.
3. Get one teammate approval, pass **Repository checks**, and resolve review conversations.
4. Squash merge the pull request.

`main` blocks direct pushes, force pushes, and deletion, including for admins.
New changes dismiss earlier approvals, and your branch must be up to date before merging.

## Commit messages

Use `type: Message` for commit messages and pull request titles.
Allowed types: `docs`, `bug`, `feat`, `patch`.

```text
docs: update setup instructions
bug: fix camera connection
feat: add obstacle detection
patch: update configuration
```

## Local setup

Install [pre-commit](https://pre-commit.com/#install) 4.7.0, then run from this repository:

```sh
pre-commit install
pre-commit run --all-files
```

Repeat `pre-commit install` for each clone.
Hooks check staged changes for secrets, private keys, merge conflicts, and invalid YAML; the commit-message hook enforces the format above.
GitHub Actions also scans Git history with Gitleaks and checks PR commits and titles.
GitHub secret scanning and push protection are enabled.
Keep credentials in ignored `.env` files; if a real secret leaks, revoke or rotate it immediately.
