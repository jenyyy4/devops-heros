# helm/clinicflow - the ClinicFlow Helm chart

This one chart deploys the full stack: ConfigMap, Secret, Postgres StatefulSet and PVC, backend and frontend Deployments and Services, Ingress, and the HPA. The ServiceMonitor and PrometheusRule are optional and switched off by default. The chart also includes NOTES.txt and a `helm test` hook.

```
helm/clinicflow/
├── Chart.yaml            chart 1.1.0, appVersion 1.0.0
├── values.yaml           defaults = local minikube (local images, clinicflow.local, backend+frontend x2, HPA 2-5 @50% CPU)
├── values-dev.yaml       fixed 2 replicas each, no HPA, smaller backend requests, debug logging
├── values-prod.yaml      GHCR images (commit-SHA tags), frontend x2, HPA 2-6 @60%, TLS ingress, existingSecret, 10Gi, monitoring on
└── templates/
    ├── _helpers.tpl      names, labels, image refs, db host, secret name
    ├── configmap.yaml    APP_NAME / LOG_LEVEL / DB_HOST / DB_PORT / DB_NAME
    ├── secret.yaml       DB_USER / DB_PASSWORD (skipped when postgres.auth.existingSecret is set; `required` guard)
    ├── postgres.yaml     headless Service + StatefulSet + volumeClaimTemplate (postgres.enabled toggle)
    ├── backend.yaml      Deployment (+wait-for-db init, startup/liveness/readiness probes, checksum annotations) + Service "backend"
    ├── frontend.yaml     Deployment (nginx-unprivileged :8080) + Service
    ├── ingress.yaml      /api -> backend, / -> frontend, optional TLS/annotations
    ├── hpa.yaml          autoscaling/v2 on CPU, scaleUp window 60s / scaleDown 120s (Deployment omits `replicas` when enabled)
    ├── servicemonitor.yaml / prometheusrule.yaml   only when the prometheus-operator CRDs exist
    ├── tests/test-connection.yaml                  `helm test`: wget backend /ready + frontend /healthz
    └── NOTES.txt
```

What changed from the chart that was copied in:

* **Ingress fixed.** It pointed at the nonexistent Service `clinicflow-backend` on port 8080. It now uses the real Service and port.
* **Postgres moved to a StatefulSet.** It used to be a Deployment with a separate PVC. It is now a StatefulSet with a `volumeClaimTemplate`, and it has a liveness probe.
* **Credentials come from the Secret.** `DATABASE_URL` used to contain the password in plain text. The backend now reads the user and password from the Secret through `secretKeyRef`.
* **New fields:** a ConfigMap, a startup probe, a securityContext (non-root, read-only root filesystem, all capabilities dropped), `checksum/config` and `checksum/secret` annotations, standard `app.kubernetes.io/*` labels, the `imagePullSecrets`, `existingSecret` and `postgres.enabled` toggles, and the frontend on port 8080.
* **HPA behaviour.** A 60s scale-up stabilization window was added after pod start-up CPU (Python imports plus Alembic) pushed the HPA to 4 replicas on an idle deploy. Scale-down uses a 120s window.
* **Two replicas by default.** Backend and frontend both start with 2 replicas, so a rolling update or node drain never takes the app down. Alembic migrations are serialised with a Postgres advisory lock, so the two backend replicas can start together safely.
* **Toggles default to off.** `serviceMonitor` and `prometheusRule` used to be on by default, which broke clusters without the CRDs. Both are now switched off by default.

## Commands used (see screenshots 50-55)

```bash
helm lint helm/clinicflow -f helm/clinicflow/values-dev.yaml
helm lint helm/clinicflow -f helm/clinicflow/values-prod.yaml
helm template clinicflow helm/clinicflow -n clinicflow | grep '^kind:' | sort | uniq -c

helm upgrade --install clinicflow ./helm/clinicflow -n clinicflow --create-namespace --wait --timeout 5m   # rev 1
helm test clinicflow -n clinicflow
BASE=http://clinicflow.local:8080 RESOLVE=clinicflow.local:8080:127.0.0.1 ./scripts/seed-demo.sh

helm upgrade clinicflow ./helm/clinicflow -n clinicflow -f helm/clinicflow/values-dev.yaml --wait   # rev 2: HPA removed, LOG_LEVEL=debug
helm rollback clinicflow 1 -n clinicflow --wait                                                    # rev 3 = rev 1 again
helm history clinicflow -n clinicflow
```

| Screenshot | Result |
|------------|--------|
| [`50`](../screenshots/50-helm-lint-template.png) | Both lints pass (`1 chart(s) linted, 0 chart(s) failed`; only `[INFO] icon is recommended`). `helm template` renders 1 ConfigMap, 2 Deployments, 1 HPA, 1 Ingress, 1 Pod (the test hook), 1 Secret, 3 Services and 1 StatefulSet |
| [`51`](../screenshots/51-helm-install.png) | `REVISION: 1`, `Install complete`; NOTES show images `clinicflow-backend:1.0.0` / `clinicflow-frontend:1.0.0` and `HPA 2-5 @ 50% CPU` |
| [`52`](../screenshots/52-helm-pods-svc-list-test.png) | 2 backend, 2 frontend and `clinicflow-postgres-0` Running; Services `backend`, `clinicflow-frontend`, `clinicflow-postgres`; HPA 2-5; PVC `data-clinicflow-postgres-0` Bound; `helm list` shows `clinicflow-1.1.0` / app `1.0.0`; `helm test` phase `Succeeded` |
| [`53`](../screenshots/53-seed-via-ingress.png) | `seed-demo.sh` through the ingress: the double booking returns HTTP 409; stats show 11 appointments, 8 patients, 5 active doctors |
| [`54`](../screenshots/54-ui-via-ingress-clinicflow-local.png) | The UI served through the ingress at `clinicflow.local` |
| [`55`](../screenshots/55-helm-upgrade-history-rollback.png) | Rev 2 with `values-dev.yaml`: no HPA, `LOG_LEVEL=debug`. Rollback to 1 creates rev 3 (`Rollback to 1`): HPA back (2-5), `LOG_LEVEL=info` |

Environments:

```bash
helm upgrade --install clinicflow helm/clinicflow -n clinicflow -f helm/clinicflow/values-dev.yaml
helm upgrade --install clinicflow helm/clinicflow -n clinicflow -f helm/clinicflow/values-prod.yaml   # needs Secret clinicflow-db-prod
```

## Gotcha: `--reuse-values` ignores new chart defaults

When I changed default probe timeouts in `values.yaml`, `helm upgrade --reuse-values` did not apply them. It reuses the values of the previous release and does not merge in the new chart's defaults. Use `--reset-then-reuse-values` (Helm 3.14 or later) when the chart's defaults have changed.

In the final state, the Helm release was uninstalled and Argo CD deploys this same chart from Git. See `../gitops/`.
