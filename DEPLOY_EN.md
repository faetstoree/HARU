# HARU — Cloud Run Deployment Guide

This document covers the complete process for deploying HARU to Google Cloud Run, including issues encountered during deployment and their fixes.

## Prerequisites

- A Google account
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed
- Git installed and code pushed to a GitHub repository

---

## Step 1: Create a GCP Project

1. Open [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown in the top left → **New Project**
3. Enter a project name (e.g. `haru-app`) → **Create**
4. Note down the **Project ID** (may differ from the name, looks like `haru-app-123456`)

---

## Step 2: Log in to gcloud locally

```cmd
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

Verify the login:

```cmd
gcloud projects describe YOUR_PROJECT_ID
```

---

## Step 3: Enable required APIs

```cmd
gcloud services enable run.googleapis.com ^
  artifactregistry.googleapis.com ^
  firestore.googleapis.com ^
  iam.googleapis.com ^
  iamcredentials.googleapis.com ^
  secretmanager.googleapis.com ^
  cloudbuild.googleapis.com
```

Wait about 30 seconds for the APIs to become active.

---

## Step 4: Create Firestore Database

**Must be done through the GCP Console UI (CLI does not support initial creation):**

1. Open directly: `https://console.cloud.google.com/datastore/setup?project=YOUR_PROJECT_ID`
2. Select **Native mode** (important — do not choose Datastore mode)
3. Set Location to **asia-northeast1** (Tokyo, same region as Cloud Run)
4. Click **Create Database**

Wait about 1 minute for creation to complete.

> **Security Rules:** The Cloud Run backend accesses Firestore using a Service Account (Admin SDK), which bypasses security rules. Keep the default settings.

---

## Step 5: Create Artifact Registry repository

```cmd
gcloud artifacts repositories create haru ^
  --repository-format=docker ^
  --location=asia-northeast1 ^
  --description="HARU app Docker images"
```

---

## Step 6: Store API keys in Secret Manager

Create secrets:

```cmd
gcloud secrets create GEMINI_API_KEY --replication-policy="automatic"
gcloud secrets create GOOGLE_MAPS_API_KEY --replication-policy="automatic"
```

Add the actual values:

```cmd
echo YOUR_GEMINI_API_KEY | gcloud secrets versions add GEMINI_API_KEY --data-file=-
echo YOUR_MAPS_API_KEY | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-
```

> If you don't have a Maps key, store an empty string as a placeholder:
> `echo "" | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-`

---

## Step 7: Create Service Account (for GitHub Actions)

```cmd
gcloud iam service-accounts create github-actions-haru ^
  --display-name="GitHub Actions HARU"
```

Get the full email (needed later):

```cmd
gcloud iam service-accounts list
```

Format: `github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com`

---

## Step 8: Grant permissions to the Service Account

Replace `YOUR_PROJECT_ID` with your actual Project ID:

```cmd
rem Cloud Run deployment
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/run.admin"

rem Push images to Artifact Registry
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/artifactregistry.writer"

rem Allow Cloud Run to act as its own SA
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/iam.serviceAccountUser"

rem Read from Secret Manager
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 9: Grant Cloud Run access to Firestore and Secrets

Get the project number:

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

Using the project number (e.g. `123456789`):

```cmd
rem Firestore read/write
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/datastore.user"

rem Secret Manager read
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 10: Configure Workload Identity Federation

Allows GitHub Actions to authenticate with GCP without a JSON key.

**Get project number:**

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

**Create WIF pool:**

```cmd
gcloud iam workload-identity-pools create "github-pool" ^
  --location="global" ^
  --display-name="GitHub Actions Pool"
```

**Create OIDC provider:**

> ⚠️ GCP now requires `--attribute-condition`, otherwise you will get:
> `ERROR: INVALID_ARGUMENT: The attribute condition must reference one of the provider's claims.`

```cmd
gcloud iam workload-identity-pools providers create-oidc "github-provider" ^
  --location="global" ^
  --workload-identity-pool="github-pool" ^
  --display-name="GitHub provider" ^
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" ^
  --issuer-uri="https://token.actions.githubusercontent.com" ^
  --attribute-condition="assertion.repository=='YOUR_GITHUB_USERNAME/HARU-main'"
```

**Bind your GitHub repo to the SA:**

```cmd
gcloud iam service-accounts add-iam-policy-binding ^
  github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com ^
  --role="roles/iam.workloadIdentityUser" ^
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_USERNAME/HARU-main"
```

**Get the full WIF Provider path (for GitHub Secrets):**

```cmd
gcloud iam workload-identity-pools providers describe github-provider ^
  --location="global" ^
  --workload-identity-pool="github-pool" ^
  --format="value(name)"
```

Output format:
`projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

---

## Step 11: Configure GitHub Secrets

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three secrets:

| Name | Value |
|---|---|
| `GCP_PROJECT_ID` | Your Project ID (e.g. `haru-app-123456`) |
| `WIF_PROVIDER` | The full path output from the last command in Step 10 |
| `WIF_SERVICE_ACCOUNT` | `github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com` |

---

## Step 12: First deployment

Confirm that `.github/workflows/deploy.yml` has `on.push.branches` set to your branch (this project uses `master`).

Push to trigger deployment:

```cmd
git add .
git commit -m "feat: add Cloud Run deployment"
git push origin master
```

Go to GitHub → **Actions** tab to monitor progress. Takes about 3–5 minutes.

---

## Step 13: Verify deployment

Go to GCP Console → [Cloud Run](https://console.cloud.google.com/run) → click the **haru** service. The URL is shown at the top of the page.

Or find the `Service URL:` line in the **Deploy to Cloud Run** step in GitHub Actions.

---

## Updating the Gemini API Key

**Option 1: Update Secret Manager (server-level key shared by all users)**

1. GCP Console → **Secret Manager** → **GEMINI_API_KEY**
2. Click **+ New Version** → paste new key → **Add Version**

Cloud Run picks up the new version automatically on the next request — no redeployment needed.

**Option 2: Set in the app UI (per-device personal key)**

In the HARU interface → **Profile** → **API Key** → enter new key → Save.

This key takes priority over the Secret Manager key and only affects your own device.

---

## Re-triggering Deployment

If you need to redeploy without any code changes:

**Option 1 (recommended):** GitHub → Actions → click the latest run → **Re-run all jobs**

**Option 2:** Push an empty commit

```cmd
git commit --allow-empty -m "ci: retrigger deployment"
git push origin master
```

---

## Migrating to Another GCP Account

Re-run Steps 3–10 in the new project, then update the GitHub Secrets (`GCP_PROJECT_ID`, `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`) with the new values and push.

To change regions, update `REGION` in `.github/workflows/deploy.yml` and make sure Firestore and Artifact Registry are created in the same region.

| Location | Region |
|---|---|
| Tokyo | `asia-northeast1` |
| Taiwan | `asia-east1` |
| Singapore | `asia-southeast1` |
| US East | `us-east1` |
