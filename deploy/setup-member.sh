#!/usr/bin/env bash
# Per-member setup: install tools, auth, connect to cluster, create namespace.
# Usage: ./deploy/setup-member.sh [namespace-prefix]
# Example: ./deploy/setup-member.sh nikhil   -> creates namespace nikhil-dev

set -e

PROJECT=alloydbbd
ZONE=us-central1-a
CLUSTER=alloydb-demo
NAME="${1:-dev}"

echo "==> Ensure gcloud, kubectl, helm are installed (brew install google-cloud-sdk kubectl helm)"
echo "==> Log in (opens browser): gcloud auth login"
read -p "Press Enter after you've run: gcloud auth login && gcloud config set project $PROJECT"

echo "==> Setting project to $PROJECT"
gcloud config set project "$PROJECT"

echo "==> Getting cluster credentials..."
gcloud container clusters get-credentials "$CLUSTER" --zone="$ZONE"

echo "==> Checking nodes..."
kubectl get nodes

NS="${NAME}-dev"
echo "==> Creating namespace $NS..."
kubectl create namespace "$NS" 2>/dev/null || echo "Namespace $NS already exists."

echo ""
echo "Done. Use your namespace with:"
echo "  kubectl get pods -n $NS"
echo "  kubectl apply -f deploy/dbcluster.yaml -n $NS"
