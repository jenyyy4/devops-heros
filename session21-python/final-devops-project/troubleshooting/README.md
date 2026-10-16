# Final Troubleshooting Challenge

There are nine intentionally broken variants of the ClinicFlow backend. For each one I applied the broken manifest, investigated it with the usual `kubectl` toolkit, found the root cause, applied the fix and verified it. All of the output below comes from real runs on the `session21` minikube cluster. The screenshots are `screenshots/80-97` (minikube profile `session21`, Kubernetes v1.37), two per scenario: broken plus investigation, then fix plus verification.

```
troubleshooting/scenarios/
├── 00-common.yaml                         namespace cf-debug, ConfigMap api-config, Secret api-db, toolbox pod
├── 01-imagepullbackoff/{broken,fixed}.yaml
├── 02-crashloop-wrong-db-password/...
├── 03-service-no-endpoints/...
├── 04-readiness-probe-wrong-path/...
├── 05-configmap-key-missing/...
├── 06-oomkilled/...
├── 07-ingress-wrong-service-port/...
├── 08-pvc-pending-storageclass/...
└── 09-hpa-missing-requests/...
```

**Why a separate namespace (`cf-debug`)?** Namespace `clinicflow` is owned by Argo CD with `selfHeal: true`. Argo would put any breakage back to the Git state before it could be investigated, which is GitOps working as intended. The scenarios therefore run in `cf-debug` and reuse the Argo-managed Postgres through cluster DNS (`clinicflow-postgres.clinicflow.svc.cluster.local`).

```bash
cd troubleshooting
kubectl apply -f scenarios/00-common.yaml
kubectl apply -f scenarios/0N-.../broken.yaml     # investigate ...
kubectl apply -f scenarios/0N-.../fixed.yaml      # fix + verify
kubectl delete ns cf-debug                        # when finished
```

## The investigation toolkit

| Question | Command |
|----------|---------|
| What state is it in? | `kubectl get pods -o wide`, `kubectl get deploy,rs,svc,ingress,pvc,hpa` |
| Why? | `kubectl describe pod/svc/ingress/pvc/hpa <name>`, then read **State / Last State / Events** |
| What happened recently? | `kubectl events --for pod/<name>` or `kubectl get events --field-selector reason=Failed` |
| What did the app say? | `kubectl logs deploy/x`, and `--previous` for the crashed container |
| Is traffic wired correctly? | `kubectl get endpointslices -l kubernetes.io/service-name=x` and `kubectl get svc x -o jsonpath='{.spec.selector}'`; then compare with `kubectl get pods --show-labels` |
| Test from inside the cluster | `kubectl exec toolbox -- wget -qO- http://svc:port/path` or `kubectl exec deploy/x -- ...` |
| Node / kernel level | `minikube ssh "sudo dmesg"` |

---

### 01: ImagePullBackOff (wrong image tag)

**Symptom.** The pod is `0/1 ImagePullBackOff`.

**Investigation** ([80](../screenshots/80-ts01-imagepullbackoff-broken.png)):

```
$ kubectl -n cf-debug get pods -l app=api
api-788c97959d-lw9wp   0/1     ImagePullBackOff   0          26s
$ kubectl -n cf-debug describe pod -l app=api | grep -E 'Image:|Reason:'
    Image:          clinicflow-backend:9.9.9
      Reason:       ImagePullBackOff
$ kubectl -n cf-debug get events --field-selector reason=Failed -o jsonpath='{range .items[*]}{.message}{"\n"}{end}' | sort -u
Error: ErrImagePull
Error: ImagePullBackOff
Failed to pull image "clinicflow-backend:9.9.9": failed to pull and unpack image "docker.io/library/clinicflow-backend:9.9.9": failed to resolve reference ...
$ minikube -p session21 image ls | grep clinicflow-backend
docker.io/library/clinicflow-backend:1.0.0
```

**Root cause.** Tag `9.9.9` was never built. The node's image store only has `clinicflow-backend:1.0.0`, so the kubelet tried Docker Hub (`docker.io/library/...`), which has no such repository.

**Fix.** Change the image to `clinicflow-backend:1.0.0`, an existing tag. In real environments, pin tags that CI has actually pushed and use `imagePullSecrets` for private registries.

**Verification** ([81](../screenshots/81-ts01-imagepullbackoff-fixed.png)). After `rollout status`, pod `api-7c8946bc8b-2f298` is ready with image `clinicflow-backend:1.0.0`, and `/ready` returns `{"status":"READY"}`.

### 02: CrashLoopBackOff (wrong DB password in the Secret)

**Symptom.** The pod is `0/1 CrashLoopBackOff`, and its restart count keeps climbing (`2 (6s ago)` after 48s).

**Investigation** ([82](../screenshots/82-ts02-crashloop-db-password-broken.png)):

```
$ kubectl -n cf-debug describe pod -l app=api | grep -A3 'Last State'
    Last State:     Terminated
      Reason:       Error
      Exit Code:    1
$ kubectl -n cf-debug logs deploy/api --previous | grep -E 'Error|FATAL' | tail -2
psycopg.OperationalError: connection failed: connection to server at "10.244.0.25", port 5432 failed: FATAL:  password authentication failed for user "clinicflow"
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection failed: ... FATAL:  password authentication failed for user "clinicflow"
$ kubectl -n clinicflow logs clinicflow-postgres-0 | grep 'password authentication failed' | tail -1
2026-10-15 11:25:26.010 UTC [728] FATAL:  password authentication failed for user "clinicflow"
$ kubectl -n cf-debug get secret api-db -o jsonpath='{.data.DB_PASSWORD}' | base64 -d
wrong-password
```

**Root cause.** Secret `api-db` holds the wrong password. `alembic upgrade head` fails on start, the container exits with code 1, and the kubelet backs off.

**Fix.** Correct the Secret, then **`kubectl rollout restart deploy/api`**. Applying `fixed.yaml` reported `deployment.apps/api unchanged`: environment variables from a Secret are only read when the container starts, so updating the Secret alone does not fix pods that are already running.

**Verification** ([83](../screenshots/83-ts02-crashloop-db-password-fixed.png)). The pod is `1/1 Running` with 0 restarts. The logs show `Application startup complete`, and `/api/appointments/stats` returns `{"date":"2026-10-15","total":11,...,"patients":8,"activeDoctors":5,...}`.

### 03: Service has no endpoints (selector mismatch)

**Symptom.** The pod is Running and Ready, but `wget http://api:8000/ready` from the toolbox pod gives `can't connect to remote host (10.110.34.213): Connection refused`.

**Investigation** ([84](../screenshots/84-ts03-service-no-endpoints-broken.png)):

```
$ kubectl -n cf-debug get pods -l app=api --show-labels
api-7c8946bc8b-8vlsp   1/1   Running   0   20s   app=api,pod-template-hash=7c8946bc8b
$ kubectl -n cf-debug get endpointslices -l kubernetes.io/service-name=api
api-ms288   IPv4   <unset>   <unset>   20s
$ kubectl -n cf-debug get svc api -o jsonpath='selector: {.spec.selector}'
selector: {"app":"backend"}
$ kubectl -n cf-debug get pods -l app=backend
No resources found in cf-debug namespace.
```

**Root cause.** The Service selector is `app=backend`, but the pods are labelled `app=api`. The selector matches nothing, so the Service has 0 endpoints.

**Fix.** Change the selector to `app: api`.

**Verification** ([85](../screenshots/85-ts03-service-no-endpoints-fixed.png)). The selector is `{"app":"api"}` and the EndpointSlice lists `10.244.0.45` on port 8000. `wget http://api:8000/ready` returns `{"status":"READY"}` and the FQDN `api.cf-debug.svc.cluster.local:8000/api/doctors` returns the doctor list.

### 04: Pod never Ready (readiness probe on the wrong path)

**Symptom.** The pod is `0/1 Running` with no restarts (still not ready after 66s), and `rollout status` times out.

**Investigation** ([86](../screenshots/86-ts04-readiness-probe-broken.png)):

```
$ kubectl -n cf-debug describe pod -l app=api | grep -E 'Readiness:|^  Ready '
    Readiness:  http-get http://:http/readyz delay=0s timeout=5s period=5s successThreshold=1 failureThreshold=3
  Ready                       False
$ kubectl -n cf-debug events --for pod/api-67ff94c4fd-rzklj | grep Unhealthy | tail -2
30s (x8 over 60s)  Warning  Unhealthy  ...  Readiness probe failed: Get "http://10.244.0.47:8000/readyz": dial tcp 10.244.0.47:8000: connect: connection refused
0s (x2 over 5s)    Warning  Unhealthy  ...  Readiness probe failed: HTTP probe failed with statuscode: 404
$ kubectl -n cf-debug logs deploy/api | grep readyz | tail -2
INFO:     10.244.0.1:59012 - "GET /readyz HTTP/1.1" 404 Not Found
INFO:     10.244.0.1:49192 - "GET /readyz HTTP/1.1" 404 Not Found
$ kubectl -n cf-debug get endpointslices -l kubernetes.io/service-name=api -o jsonpath='...ready={.conditions.ready}...'
10.244.0.47 ready=false
```

**Root cause.** The probe calls `/readyz`, but the app serves `/ready`, so every check returns 404 (the earlier `connection refused` events are from before uvicorn was listening). The pod is never marked Ready and never receives Service traffic. The liveness probe on `/health` passes, which is why there are no restarts.

**Fix.** Set `readinessProbe.httpGet.path: /ready`.

**Verification** ([87](../screenshots/87-ts04-readiness-probe-fixed.png)). The new pod is `1/1`, the endpoint shows `10.244.0.48 ready=true`, and `wget http://api:8000/ready` returns `{"status":"READY"}`.

### 05: CreateContainerConfigError (ConfigMap key missing)

**Symptom.** The pod is `0/1 CreateContainerConfigError` and the container never starts.

**Investigation** ([88](../screenshots/88-ts05-configmap-key-broken.png)):

```
$ kubectl -n cf-debug describe pod -l app=api | grep -E 'Reason:|DB_HOST:|couldn.t find key'
      Reason:       CreateContainerConfigError
      DB_HOST:       <set to the key 'DB_HOSTNAME' of config map 'api-config'>  Optional: false
  Warning  Failed     3s (x3 over 15s)  kubelet  spec.containers{api}: Error: couldn't find key DB_HOSTNAME in ConfigMap cf-debug/api-config
$ kubectl -n cf-debug get configmap api-config -o jsonpath='{.data}'
{"DB_HOST":"clinicflow-postgres.clinicflow.svc.cluster.local","DB_NAME":"clinicflow","DB_PORT":"5432"}
```

**Root cause.** The env var refers to key `DB_HOSTNAME`, but the ConfigMap only has `DB_HOST`. The reference is not optional, so the kubelet refuses to create the container.

**Fix.** Use `configMapKeyRef.key: DB_HOST`. Alternatively, add the key, or mark the reference `optional: true` if the value really is optional.

**Verification** ([89](../screenshots/89-ts05-configmap-key-fixed.png)). The pod is `1/1 Running`, `printenv DB_HOST` prints `clinicflow-postgres.clinicflow.svc.cluster.local`, and `/ready` returns `{"status":"READY"}`.

### 06: OOMKilled (memory limit too small)

**Symptom.** The pod status is `OOMKilled` and it keeps restarting (`1 (10s ago)` after 15s).

**Investigation** ([90](../screenshots/90-ts06-oomkilled-broken.png)):

```
$ kubectl -n cf-debug describe pod -l app=api | grep -E -A3 'Last State|Limits:'
    Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
    Limits:
      cpu:     300m
      memory:  40Mi
$ minikube -p session21 ssh "sudo dmesg | grep -i 'memory cgroup out of memory' | grep alembic | tail -1"
[ 5018.670854] Memory cgroup out of memory: Killed process 33873 (alembic) total-vm:63884kB, anon-rss:39344kB, file-rss:14812kB, shmem-rss:0kB, UID:10001 ...
$ kubectl -n clinicflow exec deploy/clinicflow-backend -c backend -- sh -c '... /sys/fs/cgroup/memory.current ...'
73 MiB used by a healthy pod
```

**Root cause.** The 40Mi limit is lower than what Python, Alembic, FastAPI and SQLAlchemy need at start-up. The `alembic` process (uid 10001) reached about 38 MiB of anonymous memory and a healthy pod uses about 73 MiB, so the kernel's cgroup OOM killer ends the process (exit 137 = SIGKILL).

**Fix.** Set requests to `96Mi` and the limit to `256Mi`, sized from observed usage plus headroom.

**Verification** ([91](../screenshots/91-ts06-oomkilled-fixed.png)). The pod is `1/1 Running` with 0 restarts, and `memory.current=75MiB memory.max=256MiB`.

### 07: Ingress returns 503 (wrong service port)

**Symptom.** `GET /api/doctors` through the ingress (`debug.clinicflow.local`, port-forwarded to 8080) returns **HTTP 503**, although the pod and Service are healthy.

**Investigation** ([92](../screenshots/92-ts07-ingress-port-broken.png)):

```
$ kubectl -n cf-debug describe ingress api | grep /api
                          /api   api:8080 ()          <- "()" = no endpoints behind this backend
$ kubectl -n cf-debug get svc api
api    ClusterIP   10.111.251.102   <none>   8000/TCP   23s
$ kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --tail=200 | grep cf-debug-api | tail -1
... "GET /api/doctors HTTP/1.1" 503 190 "-" "curl/8.7.1" 101 0.000 [cf-debug-api-8080] [] - - - - ...
```

**Root cause.** The Ingress backend uses `port: 8080`, but Service `api` only exposes `8000`. The controller builds an upstream `cf-debug-api-8080` with no servers in it and answers with 503.

**Fix.** Set the Ingress backend `port.number: 8000`.

**Verification** ([93](../screenshots/93-ts07-ingress-port-fixed.png)). The Ingress now shows `api:8000 (10.244.0.62:8000)`, `GET /api/doctors` returns **HTTP 200** and `/api/appointments/stats` returns JSON. The controller log shows upstream `[cf-debug-api-8000] [] 10.244.0.62:8000 591 0.029 200`.

### 08: PVC Pending (StorageClass does not exist)

**Symptom.** The PVC is `Pending` and the pod is `Pending`.

**Investigation** ([94](../screenshots/94-ts08-pvc-pending-broken.png)):

```
$ kubectl -n cf-debug describe pvc scratch-data | grep -E 'StorageClass|Status|ProvisioningFailed'
StorageClass:  fast-ssd
Status:        Pending
  Warning  ProvisioningFailed  2s (x2 over 13s)  persistentvolume-controller  storageclass.storage.k8s.io "fast-ssd" not found
$ kubectl -n cf-debug events --for pod/writer | tail -1
13s   Warning   FailedScheduling   Pod/writer   0/1 nodes are available: pod has unbound immediate PersistentVolumeClaims. ...
$ kubectl get storageclass
standard (default)   k8s.io/minikube-hostpath   Delete   Immediate   false   54m
```

**Root cause.** `storageClassName: fast-ssd` does not exist, so no provisioner creates a PV. The pod cannot be scheduled while its claim is unbound.

**Fix.** Use `storageClassName: standard`, or omit it to get the cluster default. `kubectl apply` of the fixed file is rejected with `The PersistentVolumeClaim "scratch-data" is invalid: spec: Forbidden: spec is immutable after creation ...`. Delete the Pending PVC and the pod, then apply again.

**Verification** ([95](../screenshots/95-ts08-pvc-pending-fixed.png)). The PVC is `Bound` to `pvc-4199e015-...` (256Mi, standard), the pod is `1/1 Running`, and `cat /data/hello.txt` prints the date it wrote (`Thu Oct 15 11:48:57 UTC 2026`).

### 09: HPA shows `<unknown>` (no CPU request)

**Symptom.** `kubectl get hpa` shows `cpu: <unknown>/50%` and the HPA never scales.

**Investigation** ([96](../screenshots/96-ts09-hpa-no-requests-broken.png)):

```
$ kubectl -n cf-debug get hpa api
api    Deployment/api   cpu: <unknown>/50%   1   3   1   118s
$ kubectl -n cf-debug describe hpa api | grep ScalingActive
  ScalingActive  False   FailedGetResourceMetric  the HPA was unable to compute the replica count: failed to get cpu utilization: missing request for cpu in container api of Pod api-5f958df54-84drj
$ kubectl top pod -n cf-debug -l app=api
api-5f958df54-84drj   10m   64Mi           <- metrics-server works fine
$ kubectl -n cf-debug get deploy api -o jsonpath='resources={.spec.template.spec.containers[0].resources}'
resources={}
```

**Root cause.** Utilization is calculated as usage divided by the request. The container has no CPU request, so there is nothing to divide by.

On Kubernetes 1.37 the HPA does not show the real reason straight away. For roughly the first 90 seconds it reports `did not receive metrics for targeted pods (pods might be unready)`, and only then switches to `missing request for cpu`. That is why the screenshot was taken about 2 minutes after applying `broken.yaml`.

The first attempt at breaking this scenario only removed `requests` and kept `limits`. The HPA still worked, because the API server sets requests equal to limits when only limits are given. To reproduce the failure, the whole `resources` block has to go.

**Fix.** Add `resources.requests: {cpu: 50m, memory: 96Mi}` and the limits (`cpu: 300m, memory: 256Mi`) back.

**Verification** ([97](../screenshots/97-ts09-hpa-no-requests-fixed.png)). The HPA shows `cpu: 26%/50%`, with `ScalingActive True ValidMetricFound`.

---

## Real incidents seen while building the capstone

These were not staged. They are recorded here as part of the challenge:

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `apply -k` failed: `failed calling webhook "validate.nginx.ingress.kubernetes.io"` | The ingress controller pod wasn't ready yet, straight after `addons enable ingress` | Wait for the controller, then apply again |
| Backend `Init:0/1` forever, init log said `postgres:5432 - no attempt` | `pg_isready` running as uid 10001 has no user name | `pg_isready -U probe ...` |
| `nginx: host not found in upstream "backend"` risk | The frontend nginx proxies to `http://backend:8000` | Keep the backend Service named `backend` in the manifests and the chart |
| `TLS handshake timeout`, pods restarting, metrics-server `CrashLoopBackOff`, Argo app `Unknown/Degraded` | The earlier 2-vCPU, 2.9 GB node was saturated: CPU PSI around 95%, IO PSI around 85%, swapping. Starting kube-prometheus-stack triggered it | Replaced kube-prometheus-stack with server-only Prometheus plus Grafana, scaled unused Argo components to 0, and raised the kicbase container quota (`docker update --cpus=4 --memory=3300m session21`) |
| `helm upgrade --reuse-values` did not pick up new probe timeouts | `--reuse-values` ignores new chart defaults | `--reset-then-reuse-values` |
| Error-rate panel showed "No data" instead of 0 | No `status="5xx"` series exists until the first 5xx | `(... ) or vector(0)` |
| One of two new backend pods restarted on first deploy; its log showed a duplicate table error for `alembic_version` | Both replicas started together and ran `alembic upgrade head` at the same time; both tried to create the `alembic_version` table and one crashed | `alembic/env.py` takes a Postgres advisory lock (`pg_advisory_lock`) before migrating, so the second replica waits and then finds the schema up to date. Verified with two parallel `alembic upgrade head` runs |
| HPA scaled the backend to 4 replicas on an idle deploy | Pod start-up (Python imports plus Alembic) briefly burns CPU above 50% of the request, and the HPA reacted to that spike | `behavior.scaleUp.stabilizationWindowSeconds: 60` in the chart and in `k8s/hpa.yaml` |
