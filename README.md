# HARU

AI-powered relocation support for international students in Japan: personalized roadmap (starting from airport arrival), chat assistant with maps and diagrams, and step-by-step guides.

**Repository:** https://github.com/goto-naoya/HARU.git

## Quick start (local)

```bash
cd HARU-main
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env   # set GEMINI_API_KEY or use Profile in the app
uvicorn main:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080

## Environment variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio key (optional at boot if set in Profile) |
| `USE_MOCK_API` | `false` (recommended) = use real API when a key exists |
| `GOOGLE_MAPS_API_KEY` | Optional Maps Embed API key (also configurable in Profile) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON for TTS/STT |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (optional, for logging) |
| `TTS_ENABLED` / `STT_ENABLED` | `true` to enable voice features when GCP creds exist |

## Profile settings

- **Gemini API Key** — verified before save; required for live AI chat
- **Google Maps API Key** — optional; improves embedded maps
- **API services** — shows Gemini / Maps / TTS / STT availability

## Roadmap (airport start)

Pre-departure tasks are treated as completed by default. New users begin at **arrival day** tasks (e.g. immigration, transport).

## Deploy

### Docker

```bash
docker build -t haru .
docker run -p 8080:8080 -v haru-data:/app -e GEMINI_API_KEY=your_key haru
```

Mount a volume for `agent.db` so Profile API keys persist across restarts.

### Cloud Run / Railway / Render

- Use the Dockerfile, set env vars in the dashboard
- Mount or attach persistent storage for SQLite (`agent.db`)
- For TTS/STT: attach a service account secret as `GOOGLE_APPLICATION_CREDENTIALS`

SQLite (`agent.db`) is created automatically on first run.
