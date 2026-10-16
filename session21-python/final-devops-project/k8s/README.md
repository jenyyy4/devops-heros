# k8s/ - plain manifests (Kustomize)

ClinicFlow as plain Kubernetes YAML in namespace `clinicflow`. Apply everything with `kubectl apply -k k8s/`.

| File | What it creates | Notes |
|------|-----------------|-------|
| `namespace.yaml` | Namespace `clinicflow` | |
| `configmap.yaml` | `clinicflow-config` | `DB_HOST`, `DB_PORT`, `DB_NAME`, `APP_NAME`, `LOG_LEVEL` |
| `secret.yaml` | `clinicflow-db` | `DB_USER` and `DB_PASSWORD`. These are demo values only: in a real cluster, use Sealed Secrets or External Secrets. |
| `postgres.yaml` | Headless Service and StatefulSet `postgres` | A `volumeClaimTemplate` creates the 1Gi PVC `data-postgres-0`. `PGDATA` is a subdirectory. `pg_isready` is used for both probes. |
| `backend.yaml` | Deployment (2 replicas) and Service `backend:8000` | Details below. |
| `frontend.yaml` | Deployment (2 replicas) and Service `frontend:80` (target port 8080) | Unprivileged nginx (uid 101) with a read-only root filesystem and `/tmp` as an emptyDir. |
| `ingress.yaml` | Ingress `clinicflow.local` | `/api` goes to `backend:8000` and `/` goes to `frontend:80` (ingress-nginx). |
| `hpa.yaml` | HPA `backend` | 2 to 4 replicas at 50% CPU. A 60s scale-up stabilization window ignores the start-up CPU spike, and a 60s scale-down window (default 300s) keeps the demo short. |
| `load-generator.yaml` | busybox Pod (not part of the kustomization) | Applied by hand to drive the HPA demo: 6 parallel loops on `/api/appointments/stats`. |

Details of `backend.yaml`:

* **Init container `wait-for-db`:** runs `pg_isready` until Postgres accepts connections.
* **Probes:** a startup probe on `/health` allows up to 120s (24 x 5s) for Alembic migrations, the liveness probe uses `/health` (every 15s, 5s timeout), and the readiness probe uses `/ready` (every 10s, 5s timeout), which runs a DB query.
* **Migrations:** each replica runs `alembic upgrade head` on start. `alembic/env.py` takes a Postgres advisory lock, so two replicas starting together don't race (see `../troubleshooting/`).
* **Resources:** requests of 100m CPU and 128Mi memory, limits of 500m CPU and 256Mi memory. The init container gets 10m/16Mi requests and 100m/64Mi limits.
* **Environment:** `envFrom` the ConfigMap, plus `secretKeyRef` for the credentials. `DATABASE_URL` is built from `$(DB_USER)`-style references.
* **Security:** runs as uid 10001 with `runAsNonRoot`, a read-only root filesystem, all capabilities dropped and the seccomp `RuntimeDefault` profile.

Why the backend Service is named `backend`: the frontend's nginx proxies `/api/` to `http://backend:8000`. The Service name has to match, otherwise nginx fails to resolve the upstream.

## Run it

```bash
# images built on the host and loaded into the minikube node
docker build -t clinicflow-backend:1.0.0  backend
docker build -t clinicflow-frontend:1.0.0 frontend
minikube -p session21 image load clinicflow-backend:1.0.0 clinicflow-frontend:1.0.0

kubectl apply -k k8s/
kubectl -n clinicflow rollout status statefulset/postgres
kubectl -n clinicflow rollout status deploy/backend
kubectl -n clinicflow get all,pvc,ingress

# docker driver on macOS: the node IP isn't routable, so port-forward the ingress controller
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80 &
curl --resolve clinicflow.local:8080:127.0.0.1 http://clinicflow.local:8080/api/doctors

# HPA demo
kubectl apply -f k8s/load-generator.yaml
kubectl -n clinicflow get hpa backend -w
kubectl -n clinicflow delete pod load-generator

kubectl delete -k k8s/      # clean up before installing the Helm chart
```

Results from the run on minikube profile `session21` (Kubernetes v1.37, 1 node, 4 CPUs):

| Screenshot | Shows |
|------------|-------|
| [`40`](../screenshots/40-k8s-namespace-kustomize-apply.png) | `kubectl apply -k k8s/`: 2 backend, 2 frontend and `postgres-0` all `1/1 Running` |
| [`41`](../screenshots/41-k8s-svc-ingress-endpoints.png) | Services and endpoints (2 backend, 2 frontend, 1 postgres), Ingress `clinicflow.local` at `192.168.49.2`, PVC `data-postgres-0` Bound (1Gi); `GET /` returns 200 and `/api/doctors` lists the 5 seeded doctors through the ingress |
| [`42`](../screenshots/42-k8s-probes-security-context.png) | Probes, requests/limits and the pod/container `securityContext` |
| [`43`](../screenshots/43-k8s-hpa-scale-up-under-load.png) | HPA under load: `cpu: 7%/50%` → `150%` → `425%/50%`, replicas 2 → 4; `kubectl top` shows each backend pod at 250-303m |
| [`44`](../screenshots/44-k8s-hpa-scale-down.png) | Load stopped: CPU falls to `7%/50%` and the HPA scales back from 4 to 2 |
| [`45`](../screenshots/45-k8s-delete-before-helm.png) | `kubectl delete -k k8s/` removes everything, including the namespace, before the Helm install |

## Gotchas

* **Ingress webhook not ready yet.** Applying straight after `minikube addons enable ingress` can fail with `failed calling webhook "validate.nginx.ingress.kubernetes.io"`. Wait for the controller pod, then apply again.
* **`pg_isready` as uid 10001.** There is no passwd entry for that uid, so `pg_isready` printed `no attempt`. The fix is to pass `-U probe`, which can be any user name.
* **HPA scaled an idle deploy.** Python imports plus `alembic upgrade head` burn CPU for a few seconds when a pod starts, which was enough to push the HPA to 4 replicas with no traffic at all. The fix is `behavior.scaleUp.stabilizationWindowSeconds: 60`, so a short start-up spike no longer triggers a scale-up.
* **HPA under real load.** Six request loops pushed CPU to 425% of the request and the HPA went from 2 to the maximum of 4 replicas. The load generator and Postgres also used about 270m each, so the whole node was busy during the test.
* **Leftover data on the hostPath provisioner.** The minikube hostPath provisioner can leave `Released` PVs behind, and on one run the data directory was reused. Clean up with `kubectl get pv`.
