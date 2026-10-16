# monitoring/ - Prometheus, Grafana, alerts, logs

```
monitoring/
├── prometheus-values.yaml            prometheus-community/prometheus: server only, 6h retention, scrape jobs + alert rules
├── grafana-values.yaml               grafana/grafana: Prometheus datasource, dashboard sidecar, anonymous Viewer (local only)
├── dashboards/clinicflow-dashboard.json   "ClinicFlow - Service & Bookings Overview" (13 panels)
├── kustomization.yaml                configMapGenerator -> ConfigMap clinicflow-grafana-dashboard (label grafana_dashboard=1)
├── traffic-generator.yaml            busybox pod: appointments/stats/doctors + a deliberate 404 on /api/patients/99999
└── promql.sh                         tiny CLI: instant PromQL query -> one line per series
```

## Why not kube-prometheus-stack?

kube-prometheus-stack was tried first, with Alertmanager, the default rules and the default dashboards turned off. On the earlier 2-vCPU, 2.9 GB minikube node it still ran the operator, an admission-webhook job, node-exporter, kube-state-metrics, Prometheus and Grafana with three sidecars. Together those saturated the CPU: the API server returned `TLS handshake timeout` and kube-state-metrics was stuck in `ImagePullBackOff`. It was uninstalled and replaced with:

* **`prometheus-community/prometheus`:** a single pod (prometheus-server plus the config reloader) with Alertmanager, kube-state-metrics, node-exporter and Pushgateway all disabled.
* **`grafana/grafana`:** a single pod plus the dashboard sidecar.

The Helm chart still ships an optional **ServiceMonitor** and **PrometheusRule** (`serviceMonitor.enabled` and `prometheusRule.enabled`) for clusters that run the Prometheus Operator.

## How scraping works (annotations)

The backend pod template carries `prometheus.io/scrape: "true"`, `prometheus.io/port: "8000"` and `prometheus.io/path: /metrics`. The chart's default `kubernetes-pods` job finds the pod through Kubernetes service discovery and copies the pod labels onto the series, for example `app_kubernetes_io_component="backend"`.

A trimmed `cadvisor` job scrapes the kubelet's `/metrics/cadvisor` and keeps only these series, which feed the pod CPU and memory panels:

* `container_cpu_usage_seconds_total`
* `container_memory_working_set_bytes`
* `container_spec_memory_limit_bytes`

The backend metrics come from `prometheus-fastapi-instrumentator`:

* `http_requests_total{handler,method,status="2xx|4xx|5xx"}`
* `http_request_duration_seconds_bucket{handler,method,le}`

Plus three custom business counters defined in the backend:

* `clinicflow_appointments_booked_total{specialty}`: every successful booking
* `clinicflow_appointment_status_changes_total{status}`: check-in, completion, cancellation, no-show
* `clinicflow_booking_conflicts_total`: double bookings rejected with HTTP 409

Screenshot [`61`](../screenshots/61-metrics-endpoint-in-cluster.png) reads `/metrics` from inside the cluster (`kubectl exec deploy/clinicflow-frontend -- wget -qO- http://backend:8000/metrics`) and shows both kinds, for example `clinicflow_appointments_booked_total{specialty="Cardiology"} 3.0` and the deliberate 404s as `http_requests_total{handler="/api/patients/{patient_id}",method="GET",status="4xx"} 27.0`.

## Install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm upgrade --install prometheus prometheus-community/prometheus -n monitoring --create-namespace -f monitoring/prometheus-values.yaml
helm upgrade --install grafana grafana/grafana -n monitoring -f monitoring/grafana-values.yaml
kubectl apply -k monitoring/                       # dashboard ConfigMap -> loaded by the sidecar
kubectl apply -f monitoring/traffic-generator.yaml # steady background traffic
```

Access:

```bash
kubectl -n monitoring port-forward svc/prometheus-server 9090:80 &
kubectl -n monitoring port-forward svc/grafana 3000:80 &   # admin / clinicflow-admin, or anonymous viewer
open http://localhost:3000/d/clinicflow
```

## Dashboard (13 panels, screenshot 64)

| Row | Panels |
|-----|--------|
| Service | 4 stats (backend pods up, requests/s, 5xx error rate, p95 latency) and 6 time series (request rate by endpoint, responses by status class, latency p50/p95/p99, error rate, pod CPU, pod memory) |
| Clinic bookings (business metrics) | Appointments booked by specialty (per 5m); status changes and booking conflicts (per 5m) |

## PromQL used (dashboard and screenshot 63)

| Panel | Query |
|-------|-------|
| Request rate | `sum by (method, handler) (rate(http_requests_total{namespace="clinicflow", handler!="/metrics"}[1m]))` |
| Status classes | `sum by (status) (rate(http_requests_total{namespace="clinicflow", handler!="/metrics"}[1m]))` |
| Error rate | `(sum(rate(http_requests_total{namespace="clinicflow", handler!="/metrics", status="5xx"}[5m])) or vector(0)) / clamp_min(sum(rate(http_requests_total{namespace="clinicflow", handler!="/metrics"}[5m])), 1e-9)` |
| Latency p50/p95/p99 | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="clinicflow", handler!="/metrics"}[5m])))` |
| Pod CPU | `sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="clinicflow", container!=""}[2m]))` |
| Pod memory | `sum by (pod) (container_memory_working_set_bytes{namespace="clinicflow", container!=""})` |
| Backend pods up | `sum(up{job="kubernetes-pods", namespace="clinicflow", app_kubernetes_io_component="backend"})` |
| Bookings by specialty | `sum by (specialty) (increase(clinicflow_appointments_booked_total{namespace="clinicflow"}[5m]))` |
| Status changes / conflicts | `sum by (status) (increase(clinicflow_appointment_status_changes_total{namespace="clinicflow"}[5m]))`, `sum(increase(clinicflow_booking_conflicts_total{namespace="clinicflow"}[5m]))` |

The `or vector(0)` matters. Without it, the error-rate query returns *no data* when there have been no 5xx responses yet, rather than `0`.

Real answers from `./monitoring/promql.sh` (screenshot 63):

```
sum by (handler) (rate(http_requests_total{namespace="clinicflow", handler!="/metrics"}[2m]))
{handler="/api/appointments"}  =>  0.7642
{handler="/api/doctors"}  =>  0.6087
{handler="/api/appointments/stats"}  =>  0.5944
{handler="/api/patients/{patient_id}"}  =>  0.5818      <- the deliberate 404s
{handler="/ready"}  =>  0.2095
{handler="/health"}  =>  0.1333
...
histogram_quantile(0.95, ...)                       {}  =>  0.09712   (p95 about 97 ms)
sum by (specialty) (clinicflow_appointments_booked_total)
  Pediatrics 5, Cardiology 4, Dermatology 3, General Medicine 1, Orthopedics 1
sum by (status) (clinicflow_appointment_status_changes_total)
  CANCELLED 3, CHECKED_IN 2, NO_SHOW 1
sum(clinicflow_booking_conflicts_total)             {}  =>  1
```

## Alerts (`serverFiles.alerting_rules.yml`)

The same four rules are in the chart's optional `prometheusrule.yaml` for Prometheus Operator clusters.

| Alert | Fires when | Demo |
|-------|-----------|------|
| `ClinicFlowBackendDown` (critical) | No backend pod has been scraped successfully for 1 minute | Screenshot [`65`](../screenshots/65-alert-backend-down-firing.png): no active alerts; backend scaled to 0; about 30s later `ClinicFlowBackendDown pending critical`; about 2 min later `firing`; backend scaled back to 2 and, after the rollout, no active alerts again |
| `ClinicFlowHighErrorRate` (warning) | 5xx ratio above 5% for 1 minute | Not part of this run |
| `ClinicFlowHighLatencyP95` (warning) | p95 above 500 ms for 5 minutes | See the latency observation below |
| `ClinicFlowBookingConflictSpike` (info) | More than 10 rejected double bookings in 10 minutes | Not triggered (a front-desk process or UI problem, not an outage, so severity `info`) |

Alertmanager is off to save memory. Firing alerts can be seen at `/api/v1/alerts` (Prometheus) and in Grafana.

## Observation: p95 latency spike under CPU contention

While a booking generator (a local script driving front-desk activity through the ingress) ran at the same time as the troubleshooting scenario pods, the dashboard's p95 latency rose to about **1 s** on the 4-CPU node. Once that load was gone, latency measured inside the backend pod was **2-25 ms** per request. The backend container's cgroup `cpu.stat` showed **314 throttled periods, 10.7 s throttled in total**, against its **500m CPU limit**.

So the spike was CPU throttling and contention on a shared single node, not slow queries. On a real cluster the options are to raise the CPU limit (or drop it and keep only the request), scale out sooner, or keep test workloads off the node that serves traffic. The `ClinicFlowHighLatencyP95` rule's 5-minute `for:` keeps a short spike like this from paging anyone.

## Logs

```bash
kubectl -n clinicflow logs deploy/clinicflow-backend --tail=20          # uvicorn access log (200/404/500)
kubectl -n clinicflow logs deploy/clinicflow-backend -c wait-for-db     # init container
kubectl -n clinicflow logs deploy/clinicflow-backend --previous         # after a restart
kubectl -n clinicflow events --for pod/<pod>                           # probe failures, OOMKilled, ...
```

Loki was **not** installed because there was no memory left on the node. `kubectl logs` covers the demo.

## Screenshots

| File | Shows |
|------|-------|
| [`60`](../screenshots/60-monitoring-install.png) | `prometheus-29.37.0` (Prometheus v3.15.0) and `grafana-10.5.15` (Grafana 12.3.1) deployed, both pods `2/2 Running`, dashboard ConfigMap and traffic generator applied |
| [`61`](../screenshots/61-metrics-endpoint-in-cluster.png) | Backend `/metrics` read from inside the cluster: business counters and HTTP counters |
| [`62`](../screenshots/62-prometheus-targets-up.png) | Prometheus targets UP |
| [`63`](../screenshots/63-promql-requests-bookings.png) | PromQL: request rate by handler, p95 latency, bookings by specialty, status changes, conflicts |
| [`64`](../screenshots/64-grafana-clinicflow-dashboard.png) | Grafana dashboard "ClinicFlow - Service & Bookings Overview" |
| [`65`](../screenshots/65-alert-backend-down-firing.png) | `ClinicFlowBackendDown`: inactive, pending, firing, resolved |
