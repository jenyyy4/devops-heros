# ClinicFlow: Clinic Appointment Booking, from Laptop to Monitored Kubernetes

**ClinicFlow** is a front-desk app for a multi-specialty clinic. Receptionists use it to:

- register patients
- book appointments with doctors (double-bookings are refused)
- check patients in as they arrive
- close each visit and see the day's load per doctor

The stack is React, FastAPI and PostgreSQL. Around it sits the full DevOps layer from the course: Git/GitHub, Docker, GitHub Actions CI/CD with a DevSecOps gate, GHCR, Terraform (AWS VPC + EKS), Kubernetes, Helm, Ingress, HPA, Prometheus/Grafana, Argo CD GitOps, and a troubleshooting lab.

> **Own application domain.** The course's TaskBoard reference app was only the template for the DevOps layer. ClinicFlow has its own data model (doctors, patients, appointments), its own business rules (booking conflicts, opening hours, a visit status workflow), its own UI, tests and business metrics.

Every command in this README was actually run. The screenshots in [`screenshots/`](screenshots/) come from those real runs:

- **Terminal screenshots** are rendered from the captured output.
- **Browser screenshots** were taken with headless Chrome. The address bar was added afterwards and shows the URL that was really loaded.

Environment: macOS on Apple Silicon, Docker Desktop (4 GB VM), minikube profile `session21` running Kubernetes v1.37, and the Moto AWS mock.

---

## Contents

0. [Grading rubric → evidence](#0-grading-rubric--evidence)
1. [Architecture](#1-architecture)
2. [Repository structure](#2-repository-structure)
3. [M1: The application](#3-m1-the-application)
4. [M2: Testing and code quality](#4-m2-testing-and-code-quality)
5. [M3: Git and GitHub](#5-m3-git-and-github)
6. [M4: Docker and Compose](#6-m4-docker-and-compose)
7. [M5: CI/CD with GitHub Actions](#7-m5-cicd-with-github-actions)
8. [M6: DevSecOps and Trivy](#8-m6-devsecops-and-trivy)
9. [M7: Terraform (AWS VPC + EKS)](#9-m7-terraform-aws-vpc--eks)
10. [M8: Kubernetes and Helm](#10-m8-kubernetes-and-helm)
11. [M9: Observability (Prometheus and Grafana)](#11-m9-observability-prometheus-and-grafana)
12. [GitOps with Argo CD](#12-gitops-with-argo-cd)
13. [Troubleshooting lab](#13-troubleshooting-lab)
14. [M10: Live demo script](#14-m10-live-demo-script)
15. [Known limitations](#15-known-limitations)
16. [Lessons learned](#16-lessons-learned)

---

## 0. Grading rubric → evidence

| Module | What the rubric asks for | Where it is |
|---|---|---|
| **M1** App | FastAPI `/health`; ≥4 REST endpoints; PostgreSQL table via Alembic; React UI calls the API; responsive | [`backend/app/`](backend/app/): 19 endpoints. [`alembic/versions/`](backend/alembic/versions/): 2 migrations, 3 tables. [`frontend/src/`](frontend/src/). Screenshots 02-07, 15-16 |
| **M2** Tests | pytest passes; ≥5 tests over ≥3 endpoints; test DB, not prod; `pytest.ini`/`conftest.py` | **37 tests, 100% coverage**, SQLite test DB set in [`conftest.py`](backend/tests/conftest.py), [`pytest.ini`](backend/pytest.ini). Plus 5 frontend unit tests. Screenshots 10-12 |
| **M3** Git | Public repo; meaningful commits; `.gitignore` for `.env`, `__pycache__`, `node_modules`, `.venv` | [`.gitignore`](.gitignore) plus per-app ignores. See [§5](#5-m3-git-and-github) |
| **M4** Docker | Backend Dockerfile builds; multi-stage frontend (Node → Nginx); non-root; `docker compose up --build` runs all 3 | [`backend/Dockerfile`](backend/Dockerfile) (uid 10001), [`frontend/Dockerfile`](frontend/Dockerfile) (nginx-unprivileged, uid 101), [`docker-compose.yml`](docker-compose.yml). Screenshots 13, 17, 02 |
| **M5** CI/CD | Workflow on push to `main`; pytest gates; frontend build; both images; GHCR; SHA tags | [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`cd.yml`](.github/workflows/cd.yml). Run URLs: see [§7](#7-m5-cicd-with-github-actions) |
| **M6** Trivy | Trivy on both images in CI; fails on HIGH/CRITICAL; explain a CVE / clean result | `image-scan` job and [`security/trivy.yaml`](security/trivy.yaml). Explanation in [§8](#8-m6-devsecops-and-trivy). Screenshots 20-23 |
| **M7** Terraform | Valid HCL; init; plan; VPC with 2+ public subnets; EKS + node group; destroy; `tfvars.example` | [`terraform/`](terraform/): plan **47 to add**, apply, verify, destroy **47 destroyed**. [`terraform.tfvars.example`](terraform/terraform.tfvars.example). Screenshots 30-37 |
| **M8** K8s + Helm | `k8s/namespace.yaml`; chart; `helm upgrade --install`; ≥2 replicas each; ClusterIP services; Ingress `/` and `/api`; all pods Running | [`k8s/`](k8s/), [`helm/clinicflow/`](helm/clinicflow/). Screenshots 40-55 (52 = pods, svc, `helm list`; 54 = UI through the Ingress hostname) |
| **M9** Observability | `/metrics`; Prometheus scraping (UP); Grafana; a live panel | [`monitoring/`](monitoring/). Screenshots 18, 61 (`/metrics`), 62 (Targets **UP**), 64 (Grafana dashboard with 13 panels), 65 (alert firing) |
| **M10** Docs + demo | Root README explaining the app; live demo (commit → pipeline → deployment update) | This file. Demo script in [§14](#14-m10-live-demo-script) |

---

## 1. Architecture

```mermaid
flowchart TB
    dev[Developer] -->|git push| gh[GitHub repo]
    gh --> ci

    subgraph ci[GitHub Actions: CI]
      direction LR
      lint[flake8] --> test[pytest 37 tests] --> fe[npm test + vite build]
      fe --> sast[bandit + semgrep] --> sca[pip-audit + npm audit]
      sca --> sec[gitleaks tree+history] --> df[hadolint + trivy config]
      df --> build[docker build + compose smoke test] --> scan[Trivy image gate]
    end

    scan -->|push :commit-sha| ghcr[(GHCR)]
    scan --> cd[CD: pin tag in values-prod.yaml]
    cd -->|bot commit| gh

    subgraph infra[Terraform]
      vpc[VPC 2 AZs: 2 public + 2 private subnets, NAT] --> eks[EKS + managed node group]
      ecr[ECR, optional]
    end

    subgraph k8s[Kubernetes cluster]
      argo[Argo CD] -->|helm template + sync| app
      subgraph app[namespace clinicflow]
        ing[Ingress clinicflow.local] -->|/| fesvc[frontend nginx x2]
        ing -->|/api| be[backend FastAPI x2-5]
        fesvc -->|/api proxy| be
        be --> pg[(PostgreSQL StatefulSet + PVC)]
        hpa[HPA] -.scales.-> be
      end
      subgraph mon[namespace monitoring]
        prom[Prometheus] --> graf[Grafana]
      end
      prom -.scrapes /metrics.-> be
    end

    gh -->|watched by| argo
    ghcr -->|image pull| app
    eks -.hosts.-> k8s
```

The request path is: browser → Ingress (`/` → frontend, `/api` → backend) → FastAPI → PostgreSQL. The browser never needs the backend's hostname. In Docker Compose the frontend's nginx proxies `/api` to the backend; in Kubernetes the Ingress routes it.

---

## 2. Repository structure

```text
final-devops-project/
├── backend/                  FastAPI app
│   ├── app/                  main.py, routers/ (doctors, patients, appointments), models, schemas, metrics, db, config
│   ├── alembic/versions/     0001_create_clinic_tables, 0002_seed_doctors
│   ├── tests/                37 pytest tests (conftest.py uses a throwaway SQLite DB)
│   ├── pytest.ini  .flake8  .coveragerc  requirements*.txt  Dockerfile
├── frontend/                 React 19 + Vite: src/{App,api}.js(x), views/, components/, lib/ (+ node tests), nginx.conf, Dockerfile
├── docker-compose.yml        postgres + backend + frontend, health-gated
├── k8s/                      namespace.yaml + plain manifests (Kustomize) + load generator
├── helm/clinicflow/          Helm chart (values, values-dev, values-prod, helm test)
├── terraform/                AWS root module + modules/clinicflow-infra + environments/local-mock (Moto)
├── monitoring/               Prometheus/Grafana Helm values, dashboard JSON, alert rules, PromQL helper
├── gitops/                   Argo CD AppProject + Applications, env values, local git helper
├── security/                 run-security-scans.sh (9-check gate) + scanner configs
├── troubleshooting/          9 broken/fixed scenarios + write-up
├── scripts/                  seed-demo.sh, load-test.sh, sync-root-workflows.sh
├── .github/workflows/        ci.yml, cd.yml  (standalone-repo version)
└── screenshots/              01-97, real captures
```

![project tree](screenshots/01-project-tree.png)

> **Where GitHub runs the workflows.** This project is a sub-folder of the `devops-heros` monorepo, and GitHub only runs workflows from the repo root. [`scripts/sync-root-workflows.sh`](scripts/sync-root-workflows.sh) therefore **generates** `/.github/workflows/session21-ci.yml` and `session21-cd.yml` from the files here. The generated copies add a `paths:` filter and point `APP_DIR` at this folder. If this folder becomes its own repository, the files in `.github/workflows/` work unchanged.

---

## 3. M1: The application

### Domain model

| Table | Columns | Notes |
|---|---|---|
| `doctors` | full_name, specialty, room, active | 5 doctors are seeded by migration `0002_seed_doctors` |
| `patients` | full_name, phone, email?, date_of_birth? | phone/email validated; DOB can't be in the future |
| `appointments` | patient_id → patients, doctor_id → doctors, scheduled_at, duration_minutes, reason, status, notes | indexed on doctor, patient, time and status |

### Business rules (enforced in the API, covered by tests)

* **No double-booking.** A doctor can't have two overlapping active appointments; the second one gets `409 Conflict` with the clashing appointment id. Cancelled and no-show slots are free again.
* **Opening hours.** A visit must lie entirely within 08:00-20:00, otherwise `422`.
* **Visit workflow:**
  * `SCHEDULED` → `CHECKED_IN` / `CANCELLED` / `NO_SHOW`
  * `CHECKED_IN` → `COMPLETED` / `CANCELLED`
  * Anything else gets `409`.
  * Only `SCHEDULED` visits can be rescheduled.
* **History is kept.** A patient who has appointments can't be deleted (`409`).
* Times are clinic-local wall-clock values. Timestamps that carry a timezone are rejected (`422`) instead of being silently shifted.

### REST API (19 endpoints, OpenAPI at `/docs`)

```text
GET  /  /health  /ready  /metrics
GET|POST        /api/doctors              GET|PUT        /api/doctors/{id}
GET|POST        /api/patients?search=     GET|PUT|DELETE /api/patients/{id}
GET|POST        /api/appointments?date=&status=&doctor_id=&patient_id=
GET|PUT|DELETE  /api/appointments/{id}    GET /api/appointments/stats?date=
```

`/health` is the cheap liveness check. `/ready` also queries the database, so a pod only receives traffic once the database is reachable. `/metrics` is Prometheus format and includes three **business metrics**:

* `clinicflow_appointments_booked_total{specialty}`
* `clinicflow_appointment_status_changes_total{status}`
* `clinicflow_booking_conflicts_total`

### UI

The UI is a React/Vite front-desk dashboard with three views:

* **Schedule:** day picker, KPI cards, a status-filtered schedule with Check in / Complete / No-show / Cancel actions, an "Up next" card and per-doctor load bars.
* **Patients:** search, register, remove.
* **Doctors:** mark a doctor on leave or available.

It also has a booking modal that shows API errors (such as the 409 double-booking) inline, loading and error states, and a responsive layout down to phone width.

| | |
|---|---|
| ![schedule](screenshots/02-ui-schedule-localhost-3000.png) | ![double booking rejected](screenshots/03-ui-double-booking-rejected.png) |
| ![patients](screenshots/04-ui-patients.png) | ![doctors](screenshots/05-ui-doctors.png) |
| ![mobile](screenshots/06-ui-mobile-responsive.png) | ![swagger](screenshots/07-swagger-api-docs.png) |

CRUD over curl, including a forbidden status transition, `204` delete then `404`, and the same API through the nginx proxy on `:3000` (15). The PostgreSQL tables and Alembic revision, and a join over the seeded day (16):

![api crud](screenshots/15-api-crud-curl.png)
![postgres](screenshots/16-postgres-tables-alembic.png)

### Run it locally without Docker

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
export DATABASE_URL='postgresql+psycopg://clinicflow:clinicflow@localhost:5432/clinicflow'
alembic upgrade head && uvicorn app.main:app --reload --port 8000      # http://localhost:8000/docs
cd ../frontend && npm ci && npm run dev                                # http://localhost:5173 (proxies /api)
```

---

## 4. M2: Testing and code quality

```bash
cd backend && flake8 && pytest -v --cov=app --cov-fail-under=90     # 37 passed, 100% coverage
cd frontend && npm test && npm run build                            # 5 node:test tests for the scheduling helpers
```

* [`tests/conftest.py`](backend/tests/conftest.py) sets `DATABASE_URL=sqlite:///./test.db` **before** the app is imported, and every test gets a freshly created schema. Tests never touch PostgreSQL.
* Tests cover all three resources and the ops endpoints:
  * the booking-conflict, opening-hours, timezone and status-transition rules (parametrized)
  * filters, daily stats, partial updates, 404s and 409s
  * CORS
  * the business metrics on `/metrics`
* CI fails the build if a test fails **or** coverage drops below 90%. The CI tests have to pass before any Docker image is built.

| | |
|---|---|
| ![flake8](screenshots/10-backend-lint-flake8.png) | ![frontend](screenshots/12-frontend-test-build.png) |

![pytest](screenshots/11-backend-pytest-verbose.png)

---

## 5. M3: Git and GitHub

* Repository: **https://github.com/jenyyy4/devops-heros** (public). This capstone is `session21-python/final-devops-project/`.
* `.gitignore` files exclude `.env`/`*.env` (except `.env.example`), `__pycache__/`, `node_modules/`, `.venv/`, `dist/`, `.terraform/`, `*.tfstate*`, `test.db`, coverage and report folders.
* The history has 79+ commits. The ClinicFlow rebuild is meant to go in as separate descriptive commits (backend, frontend, restructure, migration-race fix, monitoring, CI, docs), not one "update" commit.
* No secrets in history: gitleaks scans the **whole git history** of this folder in CI, and it was run locally too (screenshot 23).

---

## 6. M4: Docker and Compose

```bash
docker compose up --build            # from this folder → http://localhost:3000 (UI), http://localhost:8000/docs (API)
./scripts/seed-demo.sh               # optional: a realistic front-desk day through the API
docker compose down -v               # stop and delete the DB volume
```

| | backend | frontend |
|---|---|---|
| Build | multi-stage: deps into `/opt/venv` in a builder stage | multi-stage: `npm ci` + `vite build` on `node:24-alpine` → **nginx runtime** |
| Runtime base | `python:3.12.15-alpine3.24` + `apk upgrade`, pip removed | `nginxinc/nginx-unprivileged:1.30-alpine` + `apk upgrade` |
| User | **uid 10001** `appuser`, no shell | **uid 101**, listens on 8080 |
| Start | `alembic upgrade head && exec uvicorn …` (PID 1 gets SIGTERM) | static files + `/api` reverse proxy, security headers, gzip |
| Size | 210 MB | 91 MB |

Compose starts the services in order: `postgres` (healthy) → `backend` (healthy on `/ready`) → `frontend`.

![compose](screenshots/13-docker-compose-up-build.png)
![nonroot](screenshots/17-docker-images-nonroot.png)

---

## 7. M5: CI/CD with GitHub Actions

**CI** ([`ci.yml`](.github/workflows/ci.yml)) runs on every push and pull request to `main`, plus manual dispatch:

```text
lint (flake8) ─┐
test (pytest + coverage ≥90%) ─┤
frontend (npm test + vite build) ─┤
SAST (bandit + semgrep) ─┤
SCA (pip-audit + npm audit) ─┼─► docker build + compose smoke test ─► Trivy image gate (backend, frontend) ─► push to GHCR
secrets (gitleaks: tree + full history) ─┤                                                                    (main only)
Dockerfile lint (hadolint + trivy config) ─┘
```

* If any gate fails, the build fails and nothing is pushed.
* The smoke test starts the real Compose stack. It checks the seeded doctors, books an appointment, confirms the **same slot is rejected with 409**, reads the day's stats through the nginx proxy, and checks `/metrics` for `clinicflow_appointments_booked_total`.
* Images: `ghcr.io/<owner>/clinicflow-backend:<commit-sha>` and `…/clinicflow-frontend:<commit-sha>`. `:latest` is pushed as well, but nothing deploys `latest`.

**CD** ([`cd.yml`](.github/workflows/cd.yml)) runs only after a **successful** CI run on `main`:

1. **`gitops-update`** pins the SHA as `.backend.image.tag` / `.frontend.image.tag` in [`helm/clinicflow/values-prod.yaml`](helm/clinicflow/values-prod.yaml). It commits `chore(gitops): deploy clinicflow <sha7> [skip ci]` as `github-actions[bot]`, and Argo CD rolls the cluster forward. The pipeline never holds cluster credentials.
2. **`helm-deploy`** (optional) runs `helm upgrade --install --atomic` only if a `KUBECONFIG` secret is configured.

Commit → image → deployment is therefore traceable both ways.

All four workflow files (the two here and the two generated root copies) pass **actionlint** with no findings.

> **GitHub Actions run, GHCR and CD evidence for ClinicFlow:** *to be added after the ClinicFlow commits are pushed.*
> The workflows run automatically on that push. The README section is ready for three things:
> 1. The run URL from `gh run list --workflow "Session 21 - ClinicFlow CI"`.
> 2. The GHCR package page (`https://github.com/jenyyy4?tab=packages`) showing `clinicflow-backend`/`clinicflow-frontend` with SHA tags.
> 3. The CD bot commit.
>
> The earlier pipeline runs in this repository built the TaskBoard template, so they are not used as ClinicFlow evidence.

---

## 8. M6: DevSecOps and Trivy

[`security/run-security-scans.sh`](security/run-security-scans.sh) runs the same nine checks as CI and **blocks the release** (exit 1) if any one fails:

| Control | Tool | Fails when |
|---|---|---|
| SAST | bandit, semgrep (python/javascript/dockerfile) | MEDIUM+ bandit issue, any blocking semgrep finding |
| SCA | pip-audit, npm audit | any known Python vuln; HIGH+ npm advisory |
| Secrets | gitleaks + custom DB-URL rule | any secret, in the tree or in git history |
| Dockerfiles | hadolint, `trivy config` | any warning; HIGH+ misconfiguration |
| Images | **Trivy** on both images ([`trivy.yaml`](security/trivy.yaml)) | any **HIGH/CRITICAL CVE that has a fix**, or a secret in a layer |

**What Trivy scanned and what the result means.**

* Trivy scanned two things in each image: the OS packages of the Alpine 3.24 base, and every Python package in the backend's `/opt/venv` (screenshot 20).
* It found **0 HIGH/CRITICAL vulnerabilities in both images**. With nothing to block, the CI gate exits `0`.
* A clean scan is not proof that the images are secure. It means that no known, published CVE affects the exact package versions shipped today. New CVEs appear daily, which is why the scan runs on every build.

**Example CVE (why the base image is Alpine).** Scanning `python:3.12-slim` (Debian 13.7), the obvious alternative base, reports **44 HIGH** vulnerabilities (screenshot 21).

* Take **CVE-2026-76642** in `util-linux`/`bsdutils`: *"failed external mount helper still runs privileged X-mount post-hooks"*.
* Its status is `affected` and it has **no fixed version**, so a rebuild can't remove it. `ignore-unfixed: true` would even let it pass the gate.
* The real fix is to not ship those packages. The Alpine runtime doesn't contain util-linux's mount helpers, and the image dropped from 339 MB to 210 MB.

| | |
|---|---|
| ![trivy clean](screenshots/20-trivy-image-scan-clean.png) | ![debian slim](screenshots/21-trivy-why-not-debian-slim.png) |

![gate](screenshots/22-security-gate-all-scanners.png)
![gitleaks history](screenshots/23-gitleaks-git-history.png)

---

## 9. M7: Terraform (AWS VPC + EKS)

[`terraform/`](terraform/) describes the AWS infrastructure in `ap-south-1`. Everything lives in one in-repo module, [`modules/clinicflow-infra`](terraform/modules/clinicflow-infra), built from plain `aws_*` resources:

* **VPC** `10.20.0.0/16` across 2 AZs, with **2 public and 2 private subnets**, an Internet Gateway, a NAT Gateway, route tables and VPC flow logs.
* **EKS** 1.31 with a **managed node group** (2-4 × t3.medium) in the private subnets, KMS-encrypted secrets and IMDSv2.
* Least-privilege security groups, IAM roles, and optional ECR repositories.

Inputs are documented in [`terraform.tfvars.example`](terraform/terraform.tfvars.example); no credentials are committed. Commands for a real account:

```bash
cd terraform && cp terraform.tfvars.example terraform.tfvars
terraform init && terraform plan -out=tfplan && terraform apply tfplan
$(terraform output -raw configure_kubectl) && kubectl get nodes
terraform destroy
```

**How it was run here.** There is no AWS account available for this course, so the **same module** was applied end to end against **Moto**, a local AWS API mock, using [`environments/local-mock`](terraform/environments/local-mock). The sequence was:

1. `fmt`/`validate` on both roots
2. `init`
3. `plan`: **47 to add**
4. `apply`: 47 added
5. boto3 verification of the VPC, 2 public + 2 private subnets, NAT, EKS cluster `ACTIVE` and node group `ACTIVE`
6. Checkov: **138 passed, 0 failed**, 9 skipped, each with an inline reason
7. `destroy`: **47 destroyed**, 0 left in state

| | |
|---|---|
| ![plan](screenshots/32-terraform-plan.png) | ![apply](screenshots/33-terraform-apply.png) |
| ![verify](screenshots/35-moto-verify-vpc-eks.png) | ![destroy](screenshots/37-terraform-destroy.png) |
| ![fmt validate](screenshots/30-terraform-fmt-validate.png) | ![checkov](screenshots/36-checkov-iac-scan.png) |

Also see [31 init](screenshots/31-terraform-init.png) and [34 outputs/state](screenshots/34-terraform-output-state.png). The boto3 listing in screenshot 35 stands in for the "AWS Console" screenshot; see [§15](#15-known-limitations).

---

## 10. M8: Kubernetes and Helm

Cluster: minikube profile `session21` with the `ingress` and `metrics-server` addons. Images are loaded into the node with `minikube image load`; on EKS they are pulled from GHCR.

**Plain manifests first (k8s/).** The order was:

1. `kubectl apply -f k8s/namespace.yaml && kubectl apply -k k8s/`: 2 backend + 2 frontend pods and a Postgres StatefulSet with a PVC, with 0 restarts (40).
2. ClusterIP services, endpoints, and the Ingress answering on `clinicflow.local` (41).
3. Probes and security context checked (42).
4. HPA: the load generator pushes CPU to 425% of request and the backend scales **2 → 4**. After the load stops it scales back to **2** (43, 44).
5. Everything deleted before installing the chart (45).

**Then Helm:**

```bash
helm lint helm/clinicflow -f helm/clinicflow/values-prod.yaml
helm upgrade --install clinicflow ./helm/clinicflow --namespace clinicflow --create-namespace --wait
kubectl get pods -n clinicflow ; kubectl get svc -n clinicflow ; helm list -n clinicflow ; helm test clinicflow -n clinicflow
```

| Requirement | Result |
|---|---|
| Deployments with ≥2 replicas | backend 2 (HPA 2-5), frontend 2 |
| ClusterIP Services | `backend:8000`, `clinicflow-frontend:80`, `clinicflow-postgres:5432` (headless) |
| Ingress | `clinicflow.local`: `/api` → backend, `/` → frontend (nginx class) |
| All pods Running | 5/5 Running, 0 restarts; `helm test` **Succeeded** |
| Upgrade / rollback | rev 2 = `values-dev.yaml` (no HPA, `LOG_LEVEL=debug`) → `helm rollback 1` = rev 3 (HPA back, `info`) |

![helm evidence](screenshots/52-helm-pods-svc-list-test.png)
![ui via ingress](screenshots/54-ui-via-ingress-clinicflow-local.png)

| | |
|---|---|
| ![k8s apply](screenshots/40-k8s-namespace-kustomize-apply.png) | ![svc ingress](screenshots/41-k8s-svc-ingress-endpoints.png) |
| ![hpa up](screenshots/43-k8s-hpa-scale-up-under-load.png) | ![hpa down](screenshots/44-k8s-hpa-scale-down.png) |
| ![helm install](screenshots/51-helm-install.png) | ![upgrade rollback](screenshots/55-helm-upgrade-history-rollback.png) |

Also see [42 probes](screenshots/42-k8s-probes-security-context.png), [50 lint/template](screenshots/50-helm-lint-template.png) and [53 seeding through the Ingress](screenshots/53-seed-via-ingress.png). On macOS with the docker driver the Ingress is reached through `kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80` with `clinicflow.local` resolved to `127.0.0.1`.

**PostgreSQL in Kubernetes or on Amazon RDS?** In-cluster Postgres (a StatefulSet with a PVC) is right for this demo: it's cheap and self-contained. In production on AWS, managed RDS gives backups, point-in-time recovery, Multi-AZ failover and patching without operating them yourself. The chart already supports this: `postgres.enabled=false` plus `postgres.host`.

---

## 11. M9: Observability (Prometheus and Grafana)

```bash
helm upgrade --install prometheus prometheus-community/prometheus -n monitoring --create-namespace -f monitoring/prometheus-values.yaml
helm upgrade --install grafana grafana/grafana -n monitoring -f monitoring/grafana-values.yaml
kubectl apply -k monitoring/                         # dashboard ConfigMap, loaded by the Grafana sidecar
```

* **Scraping.** Prometheus discovers the backend pods through their `prometheus.io/*` annotations; both are **UP** (62). Cluster CPU and memory come from a trimmed cAdvisor job. The chart also ships a `ServiceMonitor` and a `PrometheusRule` for clusters that run the Prometheus Operator.
* **Dashboard "ClinicFlow - Service & Bookings Overview"** (13 panels):
  * service health: pods up, request rate per endpoint, status classes, p50/p95/p99 latency, 5xx rate, pod CPU and memory
  * **business** panels: appointments booked per specialty, and status changes plus rejected double-bookings
* **Alerts:**
  * `ClinicFlowBackendDown`: with the backend scaled to 0, it went pending → **firing** → cleared after recovery (65)
  * `ClinicFlowHighErrorRate`
  * `ClinicFlowHighLatencyP95`
  * `ClinicFlowBookingConflictSpike`

![targets](screenshots/62-prometheus-targets-up.png)
![grafana](screenshots/64-grafana-clinicflow-dashboard.png)

| | |
|---|---|
| ![metrics](screenshots/61-metrics-endpoint-in-cluster.png) | ![promql](screenshots/63-promql-requests-bookings.png) |
| ![install](screenshots/60-monitoring-install.png) | ![alert](screenshots/65-alert-backend-down-firing.png) |

**A real finding from the dashboard.** The p95 latency stat is red (about 1 s) in screenshot 64. The investigation showed:

* Measured inside a pod afterwards, the endpoints answer in 2-25 ms.
* The backend's cgroup reported **314 throttled CFS periods (10.7 s throttled)** under its 500m CPU limit.
* The spike lines up with a booking-traffic generator and the troubleshooting pods all starting on the same laptop node.

So the dashboard showed CPU contention, not slow code. The HPA reacted by scaling to 5, which is the intended behavior.

---

## 12. GitOps with Argo CD

Argo CD v3.5.4 was installed lean: dex, notifications, applicationset and the UI server were scaled to 0 to fit the 4 GB laptop VM. It tracks a Git repo: [`gitops/argocd-application.yaml`](gitops/argocd-application.yaml) points at the Helm chart plus [`gitops/apps/clinicflow/values-local.yaml`](gitops/apps/clinicflow/values-local.yaml), with automated **sync, prune and self-heal**.

| Step | What happened | Shot |
|---|---|---|
| Hand-over | `helm uninstall` (the PVC is kept) → apply AppProject + Application → `Synced/Healthy`, and the existing appointments were still there | 72 |
| Git commit | `frontend.replicaCount: 3` and `logLevel: debug` committed to Git → Argo synced on its own (2/2 → 3/3, `LOG_LEVEL=debug`) | 73 |
| Self-heal | `kubectl scale --replicas=0` and a `LOG_LEVEL=trace` patch were both reverted within seconds | 74 |
| Prune | `autoscaling.enabled: false` in Git → Argo **deleted** the HPA (`status=Pruned`) | 75 |
| Roll forward | Restore commit; the 4 Git commits match the 4 entries in Argo's sync history | 76 |

The demo source is a local Git repo served by `git daemon` ([`gitops/sync-local-repo.sh`](gitops/sync-local-repo.sh)), the Session 20 approach. The **GitHub-sourced** Application [`gitops/argocd-application-github.yaml`](gitops/argocd-application-github.yaml) watches `values-prod.yaml`, the file CD bumps. It is the end-to-end path GitHub → CI → GHCR → CD commit → Argo CD → cluster, and it is applied once the ClinicFlow commits and images are on GitHub.

| | |
|---|---|
| ![argo synced](screenshots/72-argocd-app-synced-healthy.png) | ![git commit sync](screenshots/73-argocd-git-commit-auto-sync.png) |
| ![self heal](screenshots/74-argocd-self-heal-drift.png) | ![history](screenshots/76-argocd-roll-forward-history.png) |

---

## 13. Troubleshooting lab

The brief's two exercises (a wrong image and a Service with no endpoints) are scenarios 01 and 03. The lab goes further with nine broken variants. Each was investigated with `get`, `describe`, `events`, `logs`, `endpointslices`, `exec`, `top` and `dmesg`, then root-caused, fixed and verified. The full write-up is in [`troubleshooting/README.md`](troubleshooting/README.md).

| # | Symptom | Root cause | Shots |
|---|---|---|---|
| 01 | `ImagePullBackOff` | tag `9.9.9` was never built | 80-81 |
| 02 | `CrashLoopBackOff` | wrong DB password in the Secret (needs a rollout restart after the fix) | 82-83 |
| 03 | Service has no endpoints | selector `app=backend` vs pod label `app=api` | 84-85 |
| 04 | Pod never Ready | readiness probe on `/readyz` (404) | 86-87 |
| 05 | `CreateContainerConfigError` | ConfigMap key `DB_HOSTNAME` doesn't exist | 88-89 |
| 06 | `OOMKilled` (exit 137) | 40Mi limit; a healthy pod needs about 70 MiB | 90-91 |
| 07 | Ingress returns 503 | Ingress backend port 8080, but the Service exposes 8000 | 92-93 |
| 08 | PVC `Pending` | StorageClass `fast-ssd` doesn't exist (PVC spec is immutable, so recreate it) | 94-95 |
| 09 | HPA `<unknown>` | no CPU request, so there's nothing to compute utilization against | 96-97 |

| | |
|---|---|
| ![ts01](screenshots/80-ts01-imagepullbackoff-broken.png) | ![ts03](screenshots/84-ts03-service-no-endpoints-broken.png) |
| ![ts06](screenshots/90-ts06-oomkilled-broken.png) | ![ts07](screenshots/92-ts07-ingress-port-broken.png) |

Two **real** incidents came up while building this and are fixed in the code:

1. **Migration race.** With 2 replicas, both pods ran `alembic upgrade head` at once and one crashed with `duplicate key … alembic_version`. Each migration now takes a PostgreSQL **advisory lock** ([`alembic/env.py`](backend/alembic/env.py)). Two parallel upgrades against a fresh DB were tested: both exit 0, each migration runs once, and there are 5 doctors, not 10.
2. **HPA scaled an idle app to 4.** Pod start-up (Python imports plus Alembic) briefly used about 100m CPU against a 100m request. A `scaleUp.stabilizationWindowSeconds: 60` window now ignores start-up spikes; under real load the HPA still scales (screenshot 43).

---

## 14. M10: Live demo script

Each step below covers one stage of the brief: Application → Git commit → CI pipeline → Docker image → Security scan → Registry → Terraform → Kubernetes → Helm → Ingress → Autoscaling → Monitoring → Troubleshooting.

1. **App:** open `http://clinicflow.local:8080`, book an appointment, then try the same slot again to get the 409 shown inline. Check the patient in.
2. **API and DB:** `/docs` → create/read/update/delete; `kubectl -n clinicflow exec clinicflow-postgres-0 -- psql -U clinicflow -c 'select * from appointments'`.
3. **Commit:** change something visible, for example the sidebar subtitle `Front desk` in [`frontend/src/App.jsx`](frontend/src/App.jsx), then `git commit` and `git push`.
4. **CI:** watch the Actions run with `gh run watch`: tests → build → Trivy → push. Show the SHA-tagged images in GHCR.
5. **CD:** the bot commit pins the new SHA in `values-prod.yaml`. Argo CD (the GitHub Application) syncs and the new pods roll out (`./gitops/watch-sync.sh`). Refresh the UI.
6. **Terraform:** walk through `terraform/modules/clinicflow-infra` and the plan, apply and destroy screenshots.
7. **K8s/Helm/Ingress/HPA:** `kubectl get pods,svc,ingress,hpa -n clinicflow`, `helm list -n clinicflow`; run `kubectl apply -f k8s/load-generator.yaml` and watch the HPA.
8. **Monitoring:** Grafana dashboard plus the Prometheus Targets page. Scale the backend to 0 and watch `ClinicFlowBackendDown` fire.
9. **Failure simulation:** apply `troubleshooting/scenarios/03-service-no-endpoints/broken.yaml` and debug it live.

---

## 15. Known limitations

| Item | Status |
|---|---|
| AWS Console screenshot (M7) | No AWS account is available, so Terraform ran against **Moto**. The same module and the same commands work on real AWS: `terraform/main.tf` plus a tfvars file, at about USD 5-6/day; destroy straight after grading. The boto3 listing (35) shows the VPC, subnets and an `ACTIVE` EKS cluster and node group in the mock instead. |
| GitHub Actions, GHCR and Argo-from-GitHub evidence for ClinicFlow (M5) | The workflows are ready and actionlint-clean; they run on the first push of these commits. The screenshots and run URLs are added afterwards. |
| Ingress on macOS | The docker driver's node IP isn't routable from the Mac, so the Ingress controller is port-forwarded (`:8080`) and the hostname is resolved to `127.0.0.1`. |
| In-cluster Postgres | Fine for the demo. Use RDS in production (see [§10](#10-m8-kubernetes-and-helm)). |

---

## 16. Lessons learned

* **Real replicas expose real bugs.** Going to 2 replicas immediately exposed the migration race. Running migrations from the app container is only safe with a lock; the alternative is a separate migration Job.
* **The HPA reacts to all CPU, including start-up.** A scale-up stabilization window keeps start-up spikes from adding pods.
* **Readiness is not liveness.** In scenario 04 the pod was alive but never Ready, so it never received traffic, and nothing restarted it.
* **Labels are the wiring of Kubernetes.** A one-word selector typo leaves a Service with zero endpoints and no error anywhere.
* **Pick the base image with the scanner, not by habit.** The Debian base carried 44 HIGH CVEs with no fix, so a rebuild could never clear them. Alpine cleared them.
* **GitOps changes how you operate.** Manual `kubectl` changes get reverted, and every change becomes a reviewed Git commit. The pipeline never needs cluster credentials.
* **Business metrics make a dashboard useful to the clinic.** Bookings per specialty and rejected double-bookings tell the clinic something request rates can't.
