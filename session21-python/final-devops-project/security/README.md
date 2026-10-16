# security/ — DevSecOps scans and the security gate

One script, `run-security-scans.sh`, runs every scanner the CI pipeline runs and acts as the **security gate**:
it prints a PASS/FAIL table and exits **non-zero** if any check fails, which blocks the release.
It scans `backend/` and `frontend/` (plus their Dockerfiles and images) and only needs Docker, Python 3 and npm. Scanners without a local binary run from their official images,
and bandit + pip-audit install themselves into `security/.venv` on first run.

```bash
docker compose build      # images to scan: clinicflow-{backend,frontend}:1.0.0
./security/run-security-scans.sh                       # everything; exit 1 = BLOCKED
./security/run-security-scans.sh sast sca              # or pick stages: sast|sca|secrets|dockerfile|images
SKIP_IMAGES=1 ./security/run-security-scans.sh         # before images exist
BACKEND_IMAGE=ghcr.io/me/clinicflow-backend:<sha> ./security/run-security-scans.sh images
```

Reports (JSON) go to `security/reports/`, which is gitignored.

## What runs, and what fails the gate

| Stage | Tool (version) | Config | Gate: fails when… |
|---|---|---|---|
| SAST (Python) | bandit 1.9.4 on `backend/app` | `bandit.yaml` | any **MEDIUM+** severity issue with MEDIUM+ confidence (`-ll -ii`) |
| SAST (Python/JS/Dockerfile) | semgrep 1.179.0 (`p/python`, `p/javascript`, `p/dockerfile`) | `.semgrepignore` | any *blocking* finding (`--error`) |
| SCA (backend) | pip-audit 2.10.1 | `requirements-security.txt` | **any** known vulnerability in `backend/requirements.txt` or `backend/requirements-dev.txt` |
| SCA (frontend) | npm audit | `frontend/package-lock.json` | any **HIGH/CRITICAL** advisory |
| Secrets | gitleaks v8.30.1 | `.gitleaks.toml` | **any** secret in the working tree (CI also scans git history) |
| Dockerfile lint | hadolint v2.15.1 on `backend/Dockerfile`, `frontend/Dockerfile` | `.hadolint.yaml` | any warning or error |
| Dockerfile misconfig | trivy 0.75.0 `config` | — | any HIGH/CRITICAL misconfiguration |
| Container images | trivy 0.75.0 `image` | `trivy.yaml`, `.trivyignore` | any **HIGH/CRITICAL CVE that has a fix**, or any secret baked into a layer |

`.gitleaks.toml` extends gitleaks' built-in rules with a project rule, `clinicflow-database-url-password`, which catches
database URLs that embed a password (`<scheme>://<user>:<password>@<host>`). It allowlists only the local-dev password `clinicflow` and `${VAR}`
placeholders, and it skips `node_modules/`, `.venv/`, `dist/` and the lockfiles.

Trivy uses `ignore-unfixed: true`. An OS CVE with no upstream fix can't be fixed by a rebuild, so it is reported but
doesn't block. If a risk is accepted, it goes in `.trivyignore` with an owner, a reason and a review date.

## Findings and fixes applied to the project

These were found and fixed in the shared backend/frontend Dockerfiles and dependency pins before the app was rebuilt as ClinicFlow; the fixes carried over unchanged.

| Finding (scanner) | Fix |
|---|---|
| `starlette 0.41.3` (via `fastapi 0.115.6`): 7 advisories, 16 records; `pytest 8.3.4`: 1 advisory (**pip-audit**) | bumped every pin: fastapi 0.142.2, starlette 1.7.0, uvicorn 0.54.0, SQLAlchemy 2.1.3, psycopg 3.3.6, pydantic-settings 2.15.0, alembic 1.20.0, pytest 9.1.1; test/lint deps moved to `requirements-dev.txt` |
| Wildcard CORS `allow_origins=["*"]` (**semgrep** `python.fastapi.security.wildcard-cors`) | origins now come from the `CORS_ORIGINS` setting (default: localhost:3000 and :5173); methods and headers narrowed; a test covers it |
| Frontend `package.json` used `"latest"` for every dependency (no lockfile, not reproducible) | exact versions pinned, `package-lock.json` committed, the Dockerfile uses `npm ci` |
| Frontend image ran nginx as **root** (**semgrep** `dockerfile.security.missing-user`) | runtime is `nginxinc/nginx-unprivileged:1.30-alpine`, uid 101, port 8080 |
| Backend on `python:3.12-slim` (Debian 13): **44 HIGH** OS CVEs, none fixable (**trivy**) | runtime switched to `python:3.12.15-alpine3.24`: **0** HIGH/CRITICAL, and the image went from 339 MB to 210 MB |
| `pip 25.0.1` in the image: 6 MEDIUM/LOW CVEs (**trivy**) | pip is uninstalled from both the venv and the base layer of the runtime image (it's only needed at build time) |
| `zlib 1.3.2-r0` in the nginx image: MEDIUM (**trivy**) | `apk upgrade --no-cache` in the runtime stage |
| `HEALTHCHECK` written in shell form (**hadolint** DL3025) | changed to JSON (exec) form |

## Results on the clean project

| Screenshot | Result |
|------------|--------|
| [`20`](../screenshots/20-trivy-image-scan-clean.png) | `trivy image` on `clinicflow-backend:1.0.0` (alpine 3.24.2): 0 HIGH/CRITICAL in the OS layer and in fastapi 0.142.2, starlette 1.7.0, uvicorn 0.54.0, SQLAlchemy 2.1.3, psycopg 3.3.6, prometheus-fastapi-instrumentator 8.1.0. `clinicflow-frontend:1.0.0` (alpine 3.24.2): 0. The CI gate config (`--config security/trivy.yaml`) exits 0 for both images |
| [`21`](../screenshots/21-trivy-why-not-debian-slim.png) | Why not Debian slim: `python:3.12-slim` (debian 13.7) has **44 HIGH** CVEs (0 CRITICAL), e.g. util-linux `bsdutils`, all `affected` with no fixed version |
| [`22`](../screenshots/22-security-gate-all-scanners.png) | `./security/run-security-scans.sh`: **9/9 checks PASS → `SECURITY GATE PASSED`, release allowed**. bandit: no MEDIUM+ issues in `backend/app`; semgrep: 0 blocking findings; pip-audit: no known vulnerabilities in `requirements.txt` or `requirements-dev.txt`; npm audit: 0 vulnerabilities; gitleaks: no leaks; hadolint: no warnings or errors; trivy config: 0 misconfigurations in both Dockerfiles; trivy images: CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0 in both images |
| [`23`](../screenshots/23-gitleaks-git-history.png) | gitleaks over the git history of this folder (as CI does): 3 commits scanned, no leaks found |

## Proving the gate blocks

To show the gate actually blocks, it was run against a **throwaway copy of the project in a scratch directory** (never the
real repo). The copy had a planted `app/debug_tools.py` containing a fake AWS key pair, a production DB URL with a password,
`yaml.load(..., Loader=yaml.Loader)` and `subprocess.call(..., shell=True)`, plus `PyJWT==2.3.0` and `setuptools==65.5.0`
added to `requirements.txt`. The result was **5 of 9 checks FAILED → release BLOCKED (exit 1)**:

* bandit: B602 `shell=True` (HIGH), B506 unsafe `yaml.load` (MEDIUM)
* semgrep: `avoid-pyyaml-load` and `subprocess-shell-true`
* pip-audit: 25 vulnerability records in pyjwt and setuptools
* gitleaks: 3 leaks (`aws-access-token`, `generic-api-key` and the custom `clinicflow-database-url-password`)
* trivy image: 1 CRITICAL + 7 HIGH fixable CVEs in PyJWT and setuptools, plus 2 CRITICAL secrets baked into the image layer

This blocking run was done during the original hardening and was not re-captured for the ClinicFlow screenshots. The CI workflow (`.github/workflows/ci.yml`) runs the same
tools with the same versions and thresholds, one job per stage. The image push to GHCR only runs after every gate passes.
