# HARU — AI Life Guide for International Students in Japan

**HARU** is an AI companion built for international students who have just arrived in Japan.  
From landing to settling in, HARU walks you through every administrative procedure and daily setup task — tailored to your personal situation.

> [繁體中文](./README_ZH.md) ｜ English ｜ [日本語](./README_JA.md)

---

## What Can HARU Do for You?

Arriving in Japan means a pile of bureaucratic tasks, each with its own time window and prerequisites. HARU organizes all of them into a **personalized roadmap** built around your situation, and answers your questions as you go.

### 🗺️ Personalized Settlement Roadmap

Based on your school, housing type, arrival date, part-time work plans, and more, HARU generates an ordered task list with AI-written explanations, steps, and tips for each item.

Tasks covered include:
- Ward office address registration
- National Health Insurance enrollment
- SIM card / mobile number setup
- Bank account opening
- School enrollment procedures
- Part-time work permit (資格外活動許可)
- …and more, dynamically added based on your profile

### 🤖 AI Chat Assistant "Haru"

Ask anything, get an answer instantly. Haru can:
- Look up **real-time opening hours** of nearby ward offices, banks, and phone shops
- Embed **Google Maps** navigation directly in the conversation
- Proactively suggest your next step based on current task progress
- Support **voice input and text-to-speech** (TTS / STT)

### 📋 Diagnostic Quiz

Not sure where to start? Take a short quiz and Haru will analyze your situation and generate an AI diagnosis report with clear priority recommendations.

### 📄 Action Plan PDF Export

Export your current task list and steps as a PDF — handy to bring along when visiting offices.

### 🌐 Three-Language Support

Full interface and AI response support for:
- 繁體中文 (Traditional Chinese)
- English
- 日本語 (Japanese)

---

## Getting Started

### 1. Open HARU

Open the HARU URL in your browser (provided by your administrator or deployment).

### 2. Complete Onboarding

On your first visit, fill in your basic information:

| Field | Description |
|---|---|
| School name | The Japanese school you are enrolled in |
| Arrival date | The date you entered Japan |
| Region | Prefecture or city name |
| Japanese level | Zero / Beginner / Intermediate / Advanced |
| School type | Language school / University / Vocational / High school |
| Housing type | Dormitory / Private rental / Undecided |
| Part-time plan | No / Yes / Decide later |

Check off anything you have **already completed** (e.g., received residence card, got a SIM at the airport). HARU will automatically skip those steps.

### 3. View Your Roadmap

After onboarding, the AI immediately generates your personalized roadmap. Tasks are arranged by phase and show:
- ✅ Completed tasks
- ▶️ Tasks you can start now
- 🔒 Tasks locked until prerequisites are done

Click any task to see a full description, required documents, official links, and AI-generated personalized steps.

### 4. Chat with Haru

Open the chat panel in the bottom-right corner and ask anything by text or voice, for example:

- "What time does the ward office near me open?"
- "What documents do I need for National Health Insurance?"
- "What should I do first right now?"

---

## Interface Overview

### Roadmap View

```
┌─────────────────────────────────────────────────┐
│  Phase 1  │  Phase 2  │  Phase 3  │  Phase 4    │  ← Phase tabs
├─────────────────────────────────────────────────┤
│                                                 │
│  [✅ Registration] → [▶️ Insurance] → [🔒 Bank]  │  ← Task flow
│                                                 │
├─────────────────────────────────────────────────┤
│  Task Detail Panel                              │
│  • Description / Required documents / Links     │
│  • AI personalized steps                        │
└─────────────────────────────────────────────────┘
```

### Task Status

| Status | Meaning |
|---|---|
| ✅ Completed | Task has been marked done |
| ▶️ In Progress | Available to start now |
| 🔒 Locked | Prerequisites not yet completed |
| ⏭️ Skipped | Not applicable to your situation (auto-detected) |

### Branch Choices

Some tasks branch based on your choices — for example, the "private rental" flow differs from the "dormitory" flow. HARU will prompt you to confirm choices at the right moment and adjust the subsequent task list accordingly.

---

## Settings & API Key

HARU uses the Google Gemini API to power its AI features. There are two ways to set up a key:

### Personal Key (Recommended)

In the HARU interface → **Profile (Settings)** → **API Key**, enter your own Gemini API Key.  
This key is stored on your device only and **does not affect other users**.

> Get a free key: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Server Key

If the administrator has already configured a shared server key, you can use HARU immediately without any additional setup.

### Without a Key

HARU will enter **Mock Mode**, using pre-prepared demo responses so you can explore the interface. AI personalization features will not be active.

---

## Language Switching

Use the language selector in the top-right corner to switch at any time. The entire interface and AI responses update immediately to the selected language.

---

## FAQ

**Q: Where is my data stored?**  
A: Your profile and task progress are stored in Google Cloud Firestore, identified by a device ID. No account login is required.

**Q: Will the roadmap adapt to my specific situation?**  
A: Yes. Your school type, housing choice, part-time plan, and other profile fields all affect which tasks appear and in what order. Updating your profile triggers a fresh AI roadmap generation.

**Q: Does voice input require any special setup?**  
A: Voice features are enabled server-side by the administrator. If they are unavailable, the server may not have the related Google Cloud services configured.

**Q: Can I use HARU on my phone?**  
A: Yes. HARU's interface is fully responsive and works on mobile and tablet browsers.

**Q: How accurate is the information Haru provides?**  
A: Haru's knowledge base is built from trusted official sources, and AI chat injects verified facts to reduce hallucination. That said, Japanese government procedures can change at any time — for important decisions, always verify with the relevant official website.

---

## Related Documentation

- [System Architecture](./ARCHITECTURE_EN.md) — Backend module relationships, API flows, deployment architecture
- [Deployment Guide](./DEPLOY_EN.md) — Step-by-step instructions for self-hosting on Google Cloud Run
