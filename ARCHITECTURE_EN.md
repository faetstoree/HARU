# HARU System Architecture

## Overall Architecture

```mermaid
graph TB
    subgraph Browser["🌐 Browser (SPA)"]
        HTML["index.html"]
        JS_Main["main.js<br/>Main logic / State management"]
        JS_Canvas["roadmap_canvas.js<br/>Roadmap visualization"]
        JS_Guide["guide_walkthrough.js<br/>Interactive guide"]
        JS_School["school_autocomplete.js<br/>School autocomplete"]
    end

    subgraph Static["Static Assets"]
        CSS["CSS<br/>style / haru-theme / responsive"]
        I18N_FE["locales/<br/>en / ja / zh-TW"]
    end

    subgraph FastAPI["⚡ FastAPI (main.py)"]
        direction TB
        API_Init["POST /api/user/init<br/>Onboarding"]
        API_Roadmap["POST /api/roadmap<br/>Roadmap"]
        API_Agent["POST /api/agent/step<br/>Main chat"]
        API_Chat["POST /api/chat<br/>General chat"]
        API_Quiz["POST /api/quiz/*<br/>Diagnostic quiz"]
        API_Task["POST /api/roadmap/task/*<br/>Task operations"]
        API_Schools["GET /api/schools/search"]
        API_Maps["GET /api/maps/embed-url"]
        API_TTS["POST /api/tts / /api/stt"]
        API_PDF["POST /api/roadmap/export/pdf"]
        API_Settings["GET/POST/DELETE<br/>/api/settings/api-key<br/>/api/settings/maps-key"]
    end

    Browser -->|"REST API (JSON)"| FastAPI
```

---

## Backend Module Relationships

```mermaid
graph TB
    subgraph Entry["Entry Layer"]
        MAIN["main.py<br/>FastAPI routing & startup"]
    end

    subgraph Decision["Decision Layer"]
        AGENT["agent_engine.py<br/>Rule-based / LLM routing"]
    end

    subgraph AI["🤖 AI Layer"]
        GEMINI["gemini_engine.py<br/>Gemini API wrapper<br/>Model fallback"]
        ROADMAP_AI["roadmap_ai_engine.py<br/>Onboarding AI overlay generation"]
        DETAIL_AI["roadmap_detail_engine.py<br/>Task personalization prompt"]
        QUIZ_AI["quiz_ai.py<br/>Quiz diagnosis AI"]
        ACTION_AI["action_plan_ai.py<br/>PDF action plan AI"]
        CHAT_TOOLS["chat_tools.py<br/>Gemini Function Calling"]
    end

    subgraph Roadmap["🗺️ Roadmap Layer"]
        ROADMAP["roadmap_engine.py<br/>Core roadmap logic<br/>Task status calculation"]
        BRANCH["roadmap_branch_engine.py<br/>Branch selection & supplemental tasks"]
        DETAIL["roadmap_detail_engine.py<br/>Static task expansion"]
        GRAPH["roadmap_graph_engine.py<br/>Graph / Mermaid data"]
        MERMAID["roadmap_mermaid_engine.py<br/>Mermaid diagram generation"]
        EXPORT["roadmap_export.py<br/>PDF export"]
    end

    subgraph Knowledge["📚 Knowledge Layer"]
        KNOWLEDGE["knowledge_engine.py<br/>Knowledge base queries<br/>Articles / Guides / Sources"]
        RESOURCE["resource_engine.py<br/>Official links DB<br/>Ward office URL resolution"]
    end

    subgraph Support["🔧 Support Layer"]
        QUIZ["quiz_engine.py<br/>Quiz logic"]
        SCHOOL["school_engine.py<br/>School fuzzy search"]
        MAPS["maps_engine.py<br/>Google Maps embed URL"]
        CHAT_BLOCKS["chat_blocks.py<br/>Chat message block assembly"]
        I18N["backend_i18n.py<br/>Backend i18n t()"]
    end

    subgraph Data["💾 Data Layer"]
        FIRESTORE[("Firestore<br/>users / tasks<br/>location_logs / agent_decisions")]
        JSON_DATA["Static JSON data<br/>roadmap / branches / quiz<br/>schools / resources / wards<br/>knowledge articles & guides"]
        FIRESTORE_DB["firestore_db.py<br/>Firestore access layer"]
    end

    MAIN --> AGENT
    MAIN --> ROADMAP
    MAIN --> QUIZ
    MAIN --> SCHOOL
    MAIN --> MAPS
    MAIN --> EXPORT
    AGENT --> CHAT_TOOLS
    CHAT_TOOLS --> GEMINI
    ROADMAP_AI --> GEMINI
    DETAIL_AI --> GEMINI
    QUIZ_AI --> GEMINI
    ACTION_AI --> GEMINI
    ROADMAP --> BRANCH
    ROADMAP --> GRAPH
    ROADMAP --> MERMAID
    DETAIL --> ROADMAP
    DETAIL --> BRANCH
    DETAIL --> DETAIL_AI
    EXPORT --> ACTION_AI
    DETAIL --> KNOWLEDGE
    DETAIL_AI --> KNOWLEDGE
    CHAT_TOOLS --> MAPS
    CHAT_TOOLS --> MERMAID
    CHAT_BLOCKS --> KNOWLEDGE
    CHAT_BLOCKS --> RESOURCE
    ROADMAP --> RESOURCE
    QUIZ --> QUIZ_AI
    MAIN --> CHAT_BLOCKS
    MAIN --> I18N
    FIRESTORE_DB --> FIRESTORE
    MAIN --> FIRESTORE_DB
    ROADMAP --> JSON_DATA
    BRANCH --> JSON_DATA
    KNOWLEDGE --> JSON_DATA
    RESOURCE --> JSON_DATA
    QUIZ --> JSON_DATA
    SCHOOL --> JSON_DATA
```

---

## Key Request Flows

```mermaid
sequenceDiagram
    participant Browser
    participant main as main.py
    participant roadmap as roadmap_engine
    participant resource as resource_engine
    participant agent as agent_engine
    participant chat as chat_tools
    participant gemini as gemini_engine
    participant blocks as chat_blocks
    participant knowledge as knowledge_engine
    participant db as Firestore

    Note over Browser,db: /api/user/init — Onboarding flow

    Browser->>main: POST /api/user/init (profile)
    main->>db: Create / update User
    main->>roadmap: build_roadmap_response(profile)
    roadmap->>resource: enrich_roadmap_with_official_links()
    main->>gemini: generate_ai_roadmap() [AI Overlay]
    gemini-->>main: Personalized overlay JSON
    main->>db: Save ai_roadmap cache
    main-->>Browser: Roadmap + AI overlay

    Note over Browser,db: /api/agent/step — Main chat flow

    Browser->>main: POST /api/agent/step (message)
    main->>roadmap: build_roadmap_response()
    main->>agent: should_use_llm_for_agent() → true
    main->>chat: run_chat_with_tools()
    loop Function Calling (up to 4 rounds)
        chat->>gemini: generate_with_model_fallback()
        gemini-->>chat: tool call / text
        chat->>chat: execute_chat_tool() [maps/mermaid]
    end
    main->>blocks: merge_chat_blocks()
    blocks->>knowledge: build_knowledge_blocks_for_task()
    blocks->>resource: resolve_resources_for_task()
    main-->>Browser: blocks (text + cards + chips + links)

    Note over Browser,db: /api/roadmap/task/personalize — Task personalization

    Browser->>main: POST /api/roadmap/task/personalize
    main->>knowledge: build_kb_context_for_llm()
    main->>gemini: generate personalized steps
    gemini-->>main: Personalized steps (Markdown)
    main->>resource: resolve_resources_for_task()
    main-->>Browser: Personalized steps + official links
```

---

## Data Layer

```mermaid
graph LR
    subgraph Firestore["☁️ Cloud Firestore"]
        T1[("users/{device_id}<br/>profile / API keys<br/>ai_roadmap cache")]
        T2[("users/{device_id}/tasks/{task_id}<br/>completed tasks")]
        T3[("location_logs/{device_id}<br/>latest GPS location")]
        T4[("agent_decisions/{device_id}<br/>latest decision cache")]
    end

    subgraph JSON["Static JSON (@lru_cache)"]
        J1["roadmap.json<br/>Task definitions / dependencies / phases"]
        J2["roadmap_branches.json<br/>Branch points / supplemental tasks"]
        J3["quiz_questions.json<br/>Quiz question bank"]
        J4["schools.json<br/>School list"]
        J5["official_resources.json<br/>Official links"]
        J6["regional_wards.json<br/>Ward office URLs"]
        J7["knowledge/articles.json<br/>Knowledge articles"]
        J8["knowledge/service_guides.json<br/>Interactive guides"]
        J9["knowledge/sources.json<br/>Trusted sources"]
    end

    subgraph I18N["Localization data"]
        L1["data/locales/backend/<br/>en / ja / zh-TW"]
        L2["static/locales/<br/>en / ja / zh-TW"]
    end

    firestore_db --> T1
    firestore_db --> T2
    firestore_db --> T3
    firestore_db --> T4
    roadmap_engine --> J1
    roadmap_branch_engine --> J2
    quiz_engine --> J3
    school_engine --> J4
    resource_engine --> J5
    resource_engine --> J6
    knowledge_engine --> J7
    knowledge_engine --> J8
    knowledge_engine --> J9
    backend_i18n --> L1
    frontend_js --> L2
```

---

## AI Layer and Gemini

```mermaid
graph TB
    subgraph Gemini_API["☁️ Google Gemini API"]
        M1["gemini-2.5-flash<br/>(primary)"]
        M2["gemini-2.0-flash<br/>(fallback)"]
        M3["gemini-1.5-flash<br/>(fallback)"]
        M4["gemini-2.0-flash-lite<br/>(last resort)"]
        M1 -->|"403/404 auto-downgrade"| M2
        M2 --> M3
        M3 --> M4
    end

    subgraph Key_Resolution["API Key Resolution"]
        K1["Firestore per-device key<br/>(highest priority)"]
        K2["Env var GEMINI_API_KEY<br/>(Secret Manager)"]
        K3["Mock mode<br/>(fallback when no key)"]
        K1 -->|"not found"| K2
        K2 -->|"not found"| K3
    end

    GEMINI_ENGINE["gemini_engine.py<br/>generate_with_model_fallback()"]
    GEMINI_ENGINE --> Key_Resolution
    GEMINI_ENGINE --> Gemini_API

    ROADMAP_AI["roadmap_ai_engine<br/>Onboarding overlay<br/>(generated once, cached in Firestore)"] --> GEMINI_ENGINE
    DETAIL_AI["roadmap_detail_engine<br/>Task personalization steps<br/>(real-time)"] --> GEMINI_ENGINE
    QUIZ_AI["quiz_ai<br/>Quiz diagnosis report<br/>(real-time)"] --> GEMINI_ENGINE
    ACTION_AI["action_plan_ai<br/>PDF action plan<br/>(with Google Search tool)"] --> GEMINI_ENGINE
    CHAT_TOOLS["chat_tools<br/>Function Calling chat<br/>(multi-turn, up to 4 rounds)"] --> GEMINI_ENGINE
    KNOWLEDGE["knowledge_engine<br/>Trusted facts injection<br/>(prevents AI hallucinating URLs)"] -->|"context injection"| DETAIL_AI
    KNOWLEDGE -->|"context injection"| CHAT_TOOLS
```

---

## Cloud Run Deployment Architecture

```mermaid
graph TB
    GitHub["GitHub<br/>master branch"]
    GHA["GitHub Actions<br/>deploy.yml"]
    AR["Artifact Registry<br/>Docker Image"]
    CR["Cloud Run<br/>haru service"]
    FS["Cloud Firestore<br/>asia-northeast1"]
    SM["Secret Manager<br/>GEMINI_API_KEY<br/>GOOGLE_MAPS_API_KEY"]
    WIF["Workload Identity<br/>Federation"]

    GitHub -->|"push to master"| GHA
    GHA -->|"WIF auth"| WIF
    WIF --> AR
    GHA -->|"docker build & push"| AR
    GHA -->|"gcloud run deploy"| CR
    CR -->|"read secrets"| SM
    CR -->|"read/write"| FS
    AR -->|"pull image"| CR
```
