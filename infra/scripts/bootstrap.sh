#!/usr/bin/env bash
# One-time setup before the first `terraform init` (ADR-032): the bucket that holds Terraform's
# state. Run after `gcloud auth login` and `gcloud auth application-default login`.
#   infra/scripts/bootstrap.sh <project-id> [region]
set -euo pipefail

project="${1:?usage: bootstrap.sh <project-id> [region]}"
region="${2:-us-west1}"
bucket="${project}-tfstate"

gcloud config set project "$project"
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com \
  storage.googleapis.com
if ! gcloud storage buckets describe "gs://${bucket}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${bucket}" --location="$region" \
    --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${bucket}" --versioning
echo "State bucket ready. Next:"
echo "  cd infra && terraform init -backend-config=\"bucket=${bucket}\""
