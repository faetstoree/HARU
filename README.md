# HARU

AI-powered relocation support for international students in Japan: personalized roadmap (starting from airport arrival), chat assistant with maps and diagrams, and step-by-step guides.

**Repository:** https://github.com/goto-naoya/HARU.git

## Quick start (local)

```bash
cd HARU-main
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env   # fill in GEMINI_API_KEY at minimum
uvicorn main:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080

> **Note:** Local development uses SQLite (`agent.db`) by default. Firestore is used when deployed to Cloud Run with `GOOGLE_CLOUD_PROJECT` set and valid GCP credentials.

## Environment variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio key (optional at boot if set in Profile) |
| `USE_MOCK_API` | `false` (recommended) = use real API when a key exists |
| `GOOGLE_MAPS_API_KEY` | Optional Maps Embed API key (also configurable in Profile) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID — required for Firestore on Cloud Run |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON for TTS / STT (local only) |
| `TTS_ENABLED` / `STT_ENABLED` | `true` to enable voice features when GCP creds exist |

## Profile settings

- **Gemini API Key** — verified before save; required for live AI chat
- **Google Maps API Key** — optional; improves embedded maps
- **API services** — shows Gemini / Maps / TTS / STT availability

## Roadmap (airport start)

Pre-departure tasks are treated as completed by default. New users begin at **arrival day** tasks (e.g. immigration, transport).

## Deploy

### Docker (local / self-hosted)

```bash
docker build -t haru .
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=your_key \
  -e GOOGLE_CLOUD_PROJECT=your_project_id \
  haru
```

### Cloud Run — automatic via GitHub Actions

Pushing to the `main` branch triggers `.github/workflows/deploy.yml`, which builds the Docker image, pushes it to Artifact Registry, and deploys to Cloud Run (region: `asia-northeast1`).

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `GCP_PROJECT_ID` | GCP project ID |
| `WIF_PROVIDER` | Workload Identity Federation provider resource name |
| `WIF_SERVICE_ACCOUNT` | Service account email used by WIF |
| `GEMINI_API_KEY` | Stored in Secret Manager, injected at deploy time |
| `GOOGLE_MAPS_API_KEY` | Stored in Secret Manager, injected at deploy time |

**One-time GCP setup:**

1. Enable APIs: Cloud Run, Artifact Registry, Firestore, Secret Manager
2. Create an Artifact Registry repository named `haru`
3. Configure [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) for GitHub Actions
4. Store `GEMINI_API_KEY` and `GOOGLE_MAPS_API_KEY` in Secret Manager

### Cloud Run / Railway / Render (manual)

- Use the Dockerfile, set env vars in the dashboard
- Set `GOOGLE_CLOUD_PROJECT` for Firestore
- For TTS/STT: attach a service account secret as `GOOGLE_APPLICATION_CREDENTIALS`

## Database

| Environment | Backend |
|-------------|---------|
| Local dev | SQLite (`agent.db`, created automatically on first run) |
| Cloud Run | Firestore (async, via `firestore_db.py`) |

Firestore collections: `users/{device_id}`, `users/{device_id}/tasks/{task_id}`, `location_logs/{device_id}`, `agent_decisions/{device_id}`.
