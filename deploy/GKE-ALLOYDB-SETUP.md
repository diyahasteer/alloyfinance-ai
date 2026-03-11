# GKE + AlloyDB Omni Setup Guide

Use this guide once your GCP account/quotas are available. Commands are in order.

**Project:** `alloydbbd`  
**Cluster:** `alloydb-demo`  
**Zone:** `us-central1-a`

---

## Hierarchy (reference)

```
Google Cloud (Project: alloydbbd)
   ↓
GKE Cluster (alloydb-demo)
   ↓
Nodes (VMs)
   ↓
Namespaces (e.g. <name>-dev)
   ↓
Pods
   ↓
Containers
```

---

## Part 1: One-time project setup (project owner)

### 1. Authenticate and set project

```bash
gcloud auth login alloybd1@gmail.com
```

Complete the browser flow, then:

```bash
gcloud config set account alloybd1@gmail.com
gcloud config set project alloydbbd
```

### 2. Enable required APIs

```bash
gcloud services enable container.googleapis.com \
  compute.googleapis.com \
  iam.googleapis.com \
  --project=alloydbbd
```

### 3. Create the GKE cluster

```bash
gcloud container clusters create alloydb-demo \
  --zone=us-central1-a \
  --num-nodes=2 \
  --machine-type=e2-standard-4 \
  --project=alloydbbd
```

### 4. Connect to the cluster

```bash
gcloud container clusters get-credentials alloydb-demo \
  --zone=us-central1-a \
  --project=alloydbbd
```

### 5. Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.19.1/cert-manager.yaml
```

Verify:

```bash
kubectl get pods -n cert-manager
```

### 6. Install Helm (if not installed)

```bash
brew install helm
```

### 7. Install AlloyDB Omni operator

The chart is hosted on Google Cloud Storage (the old GitHub Pages repo returns 404). Run:

```bash
# Get latest chart path and version
export HELM_PATH=$(curl -sSf https://storage.googleapis.com/alloydb-omni-operator/latest)
export OPERATOR_VERSION="${HELM_PATH%%/*}"

# Download the Helm chart
curl -sSf -o "./alloydbomni-operator-${OPERATOR_VERSION}.tgz" \
  "https://storage.googleapis.com/storage/v1/b/alloydb-omni-operator/o/$(echo ${HELM_PATH} | sed 's/\//%2F/g')?alt=media"

# Install the operator
helm install alloydbomni-operator "alloydbomni-operator-${OPERATOR_VERSION}.tgz" \
  --create-namespace \
  --namespace alloydb-omni-system \
  --timeout 5m

# Optional: remove the downloaded tgz
rm -f "./alloydbomni-operator-${OPERATOR_VERSION}.tgz"
```

If the operator’s webhooks don’t get valid certs, install the [default certificate issuers](https://cloud.google.com/alloydb/omni/kubernetes/current/docs/manage-certificates-kubernetes-operator) (see Google Cloud docs). The script does not add these by default.

Verify:

```bash
kubectl get pods -n alloydb-omni-system
```

### 8. Add team members to the project (optional)

Replace `dev@email.com` with each member’s email:

```bash
gcloud projects add-iam-policy-binding alloydbbd \
  --member="user:dev@email.com" \
  --role="roles/container.developer"
```

---

## Part 2: Each member’s local setup

### 1. Install tools

```bash
brew install google-cloud-sdk kubectl helm
```

### 2. Auth and project

```bash
gcloud auth login
gcloud config set project alloydbbd
```

### 3. Connect to the cluster

```bash
gcloud container clusters get-credentials alloydb-demo \
  --zone=us-central1-a
```

### 4. Verify

```bash
kubectl get nodes
```

If you see nodes, you’re connected.

### 5. Create your dev namespace

Replace `<name>` with your identifier (e.g. `nikhil`, `deven`):

```bash
kubectl create namespace <name>-dev
```

---

## Part 3: Using AlloyDB Omni (DBClusters)

### Create a DBCluster in your namespace

From the repo root, using the example manifest (override namespace with `-n`):

```bash
kubectl apply -f deploy/dbcluster.yaml -n <name>-dev
```

To use a custom manifest:

```bash
kubectl apply -f path/to/dbcluster.yaml -n <name>-dev
```

Each file’s `metadata.name` defines the cluster name; you can apply multiple different `dbcluster.yaml` files to get multiple clusters in the same namespace.

### Check pods in your namespace

```bash
kubectl get pods -n <name>-dev
```

### Describe a DBCluster

```bash
kubectl describe dbcluster <cluster-name> -n <name>-dev
```

Example (cluster name `my-cluster`):

```bash
kubectl describe dbcluster my-cluster -n <name>-dev
```

---

## Useful commands

### Resize cluster to zero (save cost when not using)

```bash
gcloud container clusters resize alloydb-demo \
  --num-nodes=0 \
  --zone=us-central1-a \
  --project=alloydbbd
```

### Scale back up

```bash
gcloud container clusters resize alloydb-demo \
  --num-nodes=2 \
  --zone=us-central1-a \
  --project=alloydbbd
```

Then re-run `gcloud container clusters get-credentials ...` if needed.

---

## Files in this repo

| File | Purpose |
|------|--------|
| `deploy/dbcluster.yaml` | Example AlloyDB Omni DBCluster + Secret; use with `-n <name>-dev`. |
| `deploy/setup-project.sh` | Optional script for project setup (run after auth). |
| `deploy/setup-member.sh` | Optional script for member setup. |
