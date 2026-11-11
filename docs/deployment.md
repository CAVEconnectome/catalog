# Deployment Guide

## Prerequisites

- A running CAVE GKE cluster with existing infrastructure (Cloud SQL, Redis, ingress controller)
- `terraform` CLI and access to the CAVE terraform workspace
- `helmfile` and `helm` CLI tools
- Access to the GCP project hosting the CAVE deployment
- The `cave-helm-charts` Helm repository configured

## Architecture

The catalog service is deployed as a Kubernetes Deployment with:
- **catalog container** — FastAPI/uvicorn on port 80 with Alembic migrations at startup
- **cloudsql-proxy sidecar** — proxies connections to the shared Cloud SQL instance
- **Ingress** at `/catalog` on the shared CAVE host
- **HPA** scaling between 1-3 replicas based on CPU utilization

## Infrastructure Setup (Terraform)

### 1. Database

The catalog uses a `cave_catalog` database on the shared Cloud SQL instance. This is provisioned automatically by the `local_infrastructure` module's `postgres.tf`.

### 2. Service Account & IAM

The `local_kubernetes` module provisions:
- A GCP service account: `catalog-{prefix}-{workspace}`
- Per-bucket `objectViewer` IAM bindings for credential vending
- A SA key stored in Secret Manager

Configure managed buckets in your terraform variables:

```hcl
catalog_managed_buckets = ["my-materialization-dump-bucket"]
catalog_datastacks     = ["minnie65_phase3"]
```

### 3. Apply Terraform

```bash
cd terraform-google-cave
terraform workspace select <your-workspace>
terraform apply
```

This generates `catalog.defaults.yaml` in your Helm config directory.

## Environment Variables

| Variable | Description | Source |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | ConfigMap (from Helm values) |
| `AUTH_SERVICE_URL` | Auth service URL | ConfigMap (`{globalServer}/auth`) |
| `MAT_ENGINE_URL` | Materialization engine URL | ConfigMap (`{globalServer}/materialize`) |
| `CAVECLIENT_SERVER_ADDRESS` | Global server for CAVEclient | ConfigMap |
| `DATASTACKS` | JSON list of served datastacks | ConfigMap |
| `LOG_LEVEL` | Logging level (ERROR/WARNING/INFO/DEBUG) | ConfigMap |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP SA key | Pod env (mounted secret) |
| `DAF_CREDENTIALS` | Path to CAVE token | Pod env (mounted secret) |

## IAM Roles

| Role | Scope | Purpose |
|---|---|---|
| `roles/storage.objectViewer` | Per managed bucket | Read access for credential vending (self-downscoping via CAB) |

The catalog SA does **not** need `serviceAccountTokenCreator`. It uses self-downscoping via the STS API to mint short-lived tokens with Credential Access Boundaries.

## Helm Deployment

### Helmfile Values

The terraform generates `catalog.defaults.yaml`:

```yaml
catalog:
  datastacks: ["minnie65_phase3"]
  secretFiles:
    - name: google-secret.json
      value: "ref+gcpsecrets://PROJECT_ID/catalog-google-secret-PREFIX-WORKSPACE"
    - name: cave-secret.json
      value: "ref+gcpsecrets://PROJECT_ID/CAVE_SECRET_NAME"
cloudsql:
  sqlInstanceName: "your-sql-instance"
```

### Helmfile Entry

Add to your `helmfile.yaml`:

```yaml
- name: catalog
  namespace: default
  chart: cave/catalog
  version: 0.1.0
  values:
    - cluster.yaml
    - catalog.defaults.yaml
    - cloudsql.defaults.yaml
    # - catalog.yaml  # optional user overrides
```

### Deploy

```bash
helmfile apply
```

## AFIS Integration

After deploying the catalog, add `catalog_url` to the datastack configuration in AFIS. This is optional — if not set, CAVEclient uses `{local_server}/catalog`, where the ingress routes to the service.

`catalog_url` includes the `/catalog` prefix the service is served under (e.g. `https://minnie.microns-daf.com/catalog`); CAVEclient appends `/api/v1/...` to it.

To set an explicit catalog URL:
1. Update the DataStack record in AFIS to include `catalog_url`
2. CAVEclient will auto-discover and use it when available

## Managed Bucket Onboarding

To enable credential vending for a new GCS bucket:

1. Add the bucket name to `catalog_managed_buckets` in your terraform variables:
   ```hcl
   catalog_managed_buckets = [
     "existing-bucket",
     "new-bucket-name",
   ]
   ```

2. Apply terraform:
   ```bash
   terraform apply
   ```

3. The catalog SA will receive `objectViewer` on the new bucket. Assets pointing to that bucket will automatically be registered as `managed=True` with credential vending available.

## Release Procedure

### Triggering a Release

1. Go to the `catalog` repo → Actions → "publish release" workflow
2. Click "Run workflow"
3. Select the version part to bump: `patch`, `minor`, or `major`
4. Click "Run workflow"

### What Happens Automatically

1. `bump-my-version` increments the version in `pyproject.toml` (and relocks `uv.lock`).
   The bump starts from whichever is higher, the app version or the `catalog` chart version
   in `cave-helm-charts`, so if the chart was bumped on its own the app skips ahead to match
2. A version commit and `v{version}` tag are pushed to `main`
3. A GitHub Release is created with auto-generated release notes
4. `cave-helm-charts/charts/catalog/Chart.yaml` gets the new version as both `version` and `appVersion`
5. Cloud Build triggers on the `v*` tag, builds the Docker image (reusing cached layers from
   `caveconnectome/cave-catalog:buildcache`), and pushes `docker.io/caveconnectome/cave-catalog:v{version}`

The workflow needs the `HELM_CHART_APP_ID` variable and `HELM_CHART_APP_PRIVATE_KEY` secret
(the `cave-helm-chart-updater` GitHub App) to push to `cave-helm-charts`.

### Verification

After a release:
1. Check Cloud Build logs in GCP Console for successful image build
2. Verify the image exists: `docker pull caveconnectome/cave-catalog:v{version}`
3. Update your helmfile to reference the new chart version
4. Run `helmfile apply` to deploy
5. Verify the health endpoint: `curl https://{your-host}/catalog/health`
