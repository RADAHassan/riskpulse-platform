# Security Policy

## Reporting a vulnerability

Do **not** open a public issue. Use GitHub's private
[security advisory](../../security/advisories/new) form, or contact the DevSecOps owner directly.

## Controls in place

| Control | Where | Tool |
| :--- | :--- | :--- |
| Secret scanning (full git history) | every push / PR | Gitleaks |
| Dependency & misconfiguration scan (repo files, Dockerfiles, K8s manifests) | every push / PR | Trivy (filesystem mode) |
| New vulnerable dependencies blocked in PRs | pull requests | Dependency Review |
| Automated dependency updates | weekly | Dependabot |
| Third-party GitHub Actions pinned to commit SHA | `.github/workflows/` | — |

## Planned

- SonarQube quality gate (code smells, coverage, SAST)
- Container image scanning before push (Trivy image mode)
- Kubernetes: non-root containers, read-only root filesystem, NetworkPolicies, resource limits
- Secrets delivered via Kubernetes Secrets (never in images or ConfigMaps)
