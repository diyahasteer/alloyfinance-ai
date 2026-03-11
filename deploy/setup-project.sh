#!/usr/bin/env bash
# One-time GKE + AlloyDB Omni project setup (run after gcloud auth).
# Project: alloydbbd, Cluster: alloydb-demo, Zone: us-central1-a
# Usage: ./deploy/setup-project.sh

set -e

PROJECT=alloydbbd
ZONE=us-central1-a
CLUSTER=alloydb-demo

echo "==> Setting project to $PROJECT"
gcloud config set project "$PROJECT"

echo "==> Enabling APIs..."
gcloud services enable container.googleapis.com compute.googleapis.com iam.googleapis.com --project="$PROJECT"

echo "==> Creating GKE cluster $CLUSTER (this may take several minutes)..."
gcloud container clusters create "$CLUSTER" \
  --zone="$ZONE" \
  --num-nodes=2 \
  --machine-type=e2-standard-4 \
  --project="$PROJECT"

echo "==> Getting cluster credentials..."
gcloud container clusters get-credentials "$CLUSTER" --zone="$ZONE" --project="$PROJECT"

echo "==> Installing cert-manager..."
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.19.1/cert-manager.yaml

echo "==> Waiting for cert-manager pods..."
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/instance=cert-manager -n cert-manager --timeout=120s 2>/dev/null || true

echo "==> Downloading and installing AlloyDB Omni operator (Helm chart from GCS)..."
HELM_PATH=$(curl -sSf https://storage.googleapis.com/alloydb-omni-operator/latest)
OPERATOR_VERSION="${HELM_PATH%%/*}"
curl -sSf -o "./alloydbomni-operator-${OPERATOR_VERSION}.tgz" \
  "https://storage.googleapis.com/storage/v1/b/alloydb-omni-operator/o/$(echo "${HELM_PATH}" | sed 's/\//%2F/g')?alt=media"
helm install alloydbomni-operator "alloydbomni-operator-${OPERATOR_VERSION}.tgz" \
  --create-namespace \
  --namespace alloydb-omni-system \
  --timeout 5m
rm -f "./alloydbomni-operator-${OPERATOR_VERSION}.tgz"

echo ""
echo "Done. Verify with:"
echo "  kubectl get pods -n cert-manager"
echo "  kubectl get pods -n alloydb-omni-system"
echo ""
echo "To add a team member:"
echo "  gcloud projects add-iam-policy-binding $PROJECT --member=\"user:EMAIL\" --role=\"roles/container.developer\""
