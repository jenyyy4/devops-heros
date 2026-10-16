# gitops/ - Argo CD

Argo CD deploys the **same Helm chart** (`helm/clinicflow`) from Git, using automated sync with `prune` and `selfHeal`. Nobody runs `kubectl apply` or `helm upgrade` against the cluster any more. Every change is a commit.

```
gitops/
├── argocd-application.yaml          LOCAL demo Application (applied): git://host.minikube.internal/clinicflow-gitops
├── argocd-application-github.yaml   real-world Application -> github.com/jenyyy4/devops-heros (prepared, NOT applied yet -> ns clinicflow-prod)
├── project.yaml                     AppProject "clinicflow": allowed repos + only namespaces clinicflow / clinicflow-prod
├── apps/clinicflow/values-local.yaml          environment values for the local cluster (THIS is what you edit + commit)
├── apps/clinicflow/values-prod-minikube.yaml  laptop overrides for the GitHub-sourced prod Application
├── sync-local-repo.sh               copy chart + apps/ into the local git repo, commit, start git daemon
└── watch-sync.sh                    print Argo sync/health + workload state whenever it changes
```

## Which values file does Argo CD read?

| Application | Source | Value files | Image tag keys that CD bumps |
|-------------|--------|-------------|------------------------------|
| `clinicflow` (local, applied) | `git://host.minikube.internal/clinicflow-gitops`, path `helm/clinicflow` | `values.yaml` and `../../gitops/apps/clinicflow/values-local.yaml` | `.backend.image.tag` and `.frontend.image.tag` in `gitops/apps/clinicflow/values-local.yaml` |
| `clinicflow-prod` (GitHub, **not applied yet**, ns `clinicflow-prod`) | `https://github.com/jenyyy4/devops-heros.git`, path `session21-python/final-devops-project/helm/clinicflow` | `values.yaml`, `values-prod.yaml`, `../../gitops/apps/clinicflow/values-prod-minikube.yaml` | `.backend.image.tag` and `.frontend.image.tag` in `helm/clinicflow/values-prod.yaml` |

The flow is the same in both cases. CI builds the images and pushes them to GHCR. CD commits the new tag into the values file. Argo CD notices the commit and rolls the cluster forward.

### `clinicflow-prod` is prepared but not applied

Nothing from this rebuild has been pushed to GitHub yet, so `argocd-application-github.yaml` would point at a repo that does not contain this version of the chart yet, and GHCR has no ClinicFlow images with the tag in `values-prod.yaml`. Only the local Application was applied in this run. After the push, once CI/CD has published images to GHCR:

```bash
kubectl create namespace clinicflow-prod
kubectl -n clinicflow-prod create secret generic clinicflow-db-prod \
  --from-literal=DB_USER=clinicflow --from-literal=DB_PASSWORD='<a real password>'   # values-prod.yaml uses existingSecret
kubectl apply -f gitops/project.yaml -f gitops/argocd-application-github.yaml
kubectl -n argocd get applications                                                  # clinicflow-prod -> Synced / Healthy
kubectl -n clinicflow-prod get pods,ingress                                         # host clinicflow-prod.local
```

If the GHCR packages are private, also add an `imagePullSecrets` entry (the chart supports it).

## Local Git source (no GitHub push)

This follows the Session 20 approach (`session20-.../12-gitops-argocd-demo`). A local repo is served read-only with `git daemon`. Inside minikube, `host.minikube.internal` resolves to the Mac.

```bash
GITOPS_SRC=~/gitops-src ./gitops/sync-local-repo.sh 'initial: clinicflow chart + local env values'   # repo = $GITOPS_SRC/clinicflow-gitops
kubectl -n argocd exec deploy/argocd-repo-server -- git ls-remote git://host.minikube.internal/clinicflow-gitops
```

In screenshot [`71`](../screenshots/71-gitops-local-git-repo.png) the first commit is `8824e56`; the repo holds `helm/clinicflow/**` plus `gitops/apps/clinicflow/*.yaml`, and the repo-server sees `8824e56b...` as `HEAD` and `refs/heads/main`.

## Install (lean, screenshot 70)

```bash
curl -sSLo argocd-install-v3.5.4.yaml https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.4/manifests/install.yaml
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f argocd-install-v3.5.4.yaml
kubectl -n argocd scale deploy argocd-dex-server argocd-notifications-controller argocd-applicationset-controller argocd-server --replicas=0
kubectl -n argocd patch cm argocd-cm --type merge -p '{"data":{"timeout.reconciliation":"30s"}}'
kubectl -n argocd rollout status deploy/argocd-repo-server
kubectl -n argocd rollout status statefulset/argocd-application-controller
```

Only the application controller, repo-server and Redis keep running. `argocd-server` (the UI and API) is scaled to 0 to save memory on the 4 GB VM; everything in this demo uses `kubectl -n argocd get applications` or the Application status. To use the UI, scale it back up and port-forward it:

```bash
kubectl -n argocd scale deploy argocd-server --replicas=1
kubectl -n argocd port-forward svc/argocd-server 8443:443
```

Get the admin password with:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```

## Demo (screenshots 70-76)

| Step | What was done | What happened (real output) |
|------|---------------|-----------------------------|
| 1. Handover from Helm ([72](../screenshots/72-argocd-app-synced-healthy.png)) | `helm uninstall clinicflow`, then `kubectl apply -f gitops/project.yaml -f gitops/argocd-application.yaml` | The PVC `data-clinicflow-postgres-0` (same volume `pvc-033e1673-...`) survived the uninstall. `watch-sync.sh`: `OutOfSync/Missing` → `Synced/Progressing` → a `Synced/Degraded` flap → `Synced/Healthy` at `8824e56` (18:05:21 → 18:08:01). 2+2 pods Running and `/api/appointments/stats` still returns the 11 appointments seeded before the handover |
| 2. Git commit → auto sync ([73](../screenshots/73-argocd-git-commit-auto-sync.png)) | In `values-local.yaml`: `frontend.replicaCount` 2 → 3, `config.logLevel` info → debug; committed as `270c48d` | `OutOfSync` at 18:09:09, frontend `3/3` at 18:09:11, ConfigMap `LOG_LEVEL=debug`, app `Synced` at `270c48dc...` |
| 3. Self-heal ([74](../screenshots/74-argocd-self-heal-drift.png)) | `kubectl scale deploy clinicflow-frontend --replicas=0`, then `kubectl patch cm clinicflow-config` with `LOG_LEVEL=trace` | Frontend back to `3/3` within about 5s (18:09:21 → 18:09:26). `LOG_LEVEL` was `trace` at 18:09:26 and back to `debug` (the Git value) at 18:09:29. App `Synced/Healthy` |
| 4. Prune ([75](../screenshots/75-argocd-prune-hpa.png)) | Commit `cedc031` sets `autoscaling.enabled: false` | HPA `clinicflow-backend` (2-3) deleted; sync result `HorizontalPodAutoscaler/clinicflow-backend: status=Pruned` |
| 5. Roll forward ([76](../screenshots/76-argocd-roll-forward-history.png)) | Commit `ff56a76` restores frontend 2 replicas, log level info and the HPA | Frontend `2/2`, HPA recreated. `git log` (`8824e56`, `270c48d`, `cedc031`, `ff56a76`) matches the Application `status.history` ids 0-3 one to one |

Rolling *back* is done the same way: revert the commit in Git and Argo CD syncs to it.

To make Argo poll immediately instead of waiting up to 30s:

```bash
kubectl -n argocd annotate app clinicflow argocd.argoproj.io/refresh=normal --overwrite
```

## Gotchas

* **Ordering.** Argo CD can adopt resources, but leaving a Helm release *and* an Application on the same objects means two owners. Uninstall the Helm release first.
* **Load on the node.** On the earlier 2-vCPU node the repo-server crash-looped and the API server restarted several times. While the controller couldn't reach the repo-server, the app showed `Unknown/Degraded` with `ComparisonError: lookup argocd-repo-server ... i/o timeout`. Once the load dropped, the app returned to `Synced/Healthy` without any manual sync. With the lean install above (4 components scaled to 0) on the 4 GB `session21` VM, this did not happen in the run shown in screenshots 70-76.
* **HPA health.** Argo marks an HPA as `Degraded` while it has no metrics yet (`cpu: <unknown>`, for example just after the pods start). That is the most likely cause of the short `Synced/Degraded` flap in step 1.
