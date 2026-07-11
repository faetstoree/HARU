"""Central model / API configuration for Haru."""

# --- Google Gemini (google-genai) ---
# Used for: agent step (when user reports a problem), chat, form image analysis
GEMINI_MODEL = "gemini-2.5-flash"
# Tried in order when the primary model returns 403/404 (API key tier / region differences)
GEMINI_MODEL_FALLBACKS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
]

# --- Google Cloud Text-to-Speech ---
TTS_VOICES = {
    "zh-TW": ("cmn-TW", "cmn-TW-Wavenet-A"),
    "en": ("en-US", "en-US-Journey-F"),
    "ja": ("ja-JP", "ja-JP-Neural2-B"),
}

# --- Google Cloud Speech-to-Text ---
STT_LANGUAGE_CODES = {
    "zh-TW": "zh-TW",
    "en": "en-US",
    "ja": "ja-JP",
}
STT_AUDIO_ENCODING = "WEBM_OPUS"
STT_SAMPLE_RATE_HZ = 48000

# --- Rule-based (no API) ---
# Roadmap state, task completion, official link chips, default agent guidance
