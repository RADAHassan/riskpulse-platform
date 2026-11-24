# Contributing

## Branches

| Branch | Role | Rules |
| :--- | :--- | :--- |
| `main` | Always deployable, what we demo | Protected: PR only, 1 approval, CI green |
| `develop` | Integration of finished features | Protected: PR only, CI green |
| `feat/<area>-<short-desc>` | New work | Branch from `develop`, PR back to `develop` |
| `fix/<area>-<short-desc>` | Bug fix | Same as above |
| `hotfix/<short-desc>` | Urgent fix on `main` | PR to `main`, then merge `main` back into `develop` |

`<area>` is one of: `backend`, `frontend`, `ml`, `mlops`, `infra`, `ci`, `docs`.

Examples: `feat/backend-transaction-service`, `feat/infra-hpa`, `fix/frontend-login-redirect`.

## Commits — Conventional Commits

```
<type>(<scope>): <short summary in imperative mood>
```

- **type**: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`
- **scope**: the area or service, e.g. `auth-service`, `risk-service`, `ml`, `k8s`, `grafana`

Examples:
```
feat(transaction-service): add POST /transactions endpoint
ci(security): add Trivy image scan
fix(ml-serving): return model version in /predict response
```

## Pull requests

1. Keep PRs small and focused on one area.
2. Fill in the PR template (what, why, how it was tested).
3. CI must be green. CODEOWNERS of the touched folders are requested automatically.
4. Squash-merge; the PR title becomes the commit message, so it must follow Conventional Commits.

## Never commit

- Secrets (passwords, tokens, API keys, `.env`, kubeconfig). Use `.env.example` and Kubernetes Secrets.
- Raw datasets (`data/`), virtual environments, build outputs (`target/`, `node_modules/`, `dist/`).

If a secret is pushed by mistake: tell the DevSecOps owner immediately and **revoke the secret** —
deleting the commit is not enough.

## Releases

Tags follow SemVer per component prefix when needed: `ml-v2.3.8`, `platform-v1.0.0`.
