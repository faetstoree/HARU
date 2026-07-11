let uiTranslations = {};
const agentFaces = {
    "welcome": "H",
    "thinking": "H",
    "guiding": "H",
    "alert": "!",
    "success": "H"
};

let currentLang = localStorage.getItem('currentLang') || 'en';
let schoolInfo = JSON.parse(localStorage.getItem('schoolInfo')) || null;
let completedTasks = JSON.parse(localStorage.getItem('completedTasks')) || [];
let chatHistory = JSON.parse(localStorage.getItem('chatHistory')) || [];

function getOrCreateDeviceId() {
    let devId = localStorage.getItem('deviceId');
    if (!devId) {
        devId = 'device_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
        localStorage.setItem('deviceId', devId);
    }
    return devId;
}

let deviceId = getOrCreateDeviceId();

let currentGPS = { latitude: null, longitude: null, address: "Unknown" };
let currentAgentAction = null;
let currentDecisionObj = JSON.parse(localStorage.getItem('currentDecisionObj')) || null;
let currentAbortController = null;

let roadmapData = null;
let selectedTaskId = null;
let selectedPhaseId = null;
let onboardTaskSchema = [];

let isVoiceEnabled = false;
let audioContext = null;
let mediaRecorder = null;
let audioChunks = [];

let clockTimerId = null;
let locationTimerId = null;
let lastSpokenNarrative = '';
let lastAgentFingerprint = null;

const MAX_CHAT_IMAGES = 4;
let chatPendingImages = [];
let quizState = null;
let branchChoices = JSON.parse(localStorage.getItem('branchChoices')) || {};
let taskExpansionCache = {};
let taskPersonalizedCache = {};
let roadmapFullscreen = false;
let currentPdfBlobUrl = null;
// When the user clicks a phase tab, suppress the auto-scroll-to-focus in renderRoadmap.
// Cleared after one render cycle so subsequent data refreshes can scroll normally.
let _suppressFocusScroll = false;

async function loadTranslations(lang) {
    if (uiTranslations[lang]) return;
    try {
        const res = await fetch(`/static/locales/${lang}.json?v=1.5`);
        uiTranslations[lang] = await res.json();
        window.uiTranslations = uiTranslations;
    } catch (e) {
        console.error(`Failed to load translations for ${lang}`, e);
        uiTranslations[lang] = {};
    }
    window.uiTranslations = uiTranslations;
}

let roadmapCanvas = null;

const JOURNEY_TASK_ICONS = {
    task_immigration: 'badge',
    task_residence_card: 'badge',
    task_phone: 'sim_card',
    task_ward_office: 'location_city',
    task_resident_reg_complete: 'how_to_reg',
    task_bank: 'account_balance',
    task_school_enroll: 'school',
    task_move_in: 'home',
    task_transport: 'directions_transit',
    task_visa_apply: 'description',
    task_coe_receive: 'mail',
};

function taskJourneyIcon(taskId) {
    if (JOURNEY_TASK_ICONS[taskId]) return JOURNEY_TASK_ICONS[taskId];
    if (taskId.includes('phone') || taskId.includes('sim')) return 'sim_card';
    if (taskId.includes('bank')) return 'account_balance';
    if (taskId.includes('ward') || taskId.includes('address')) return 'location_city';
    if (taskId.includes('school') || taskId.includes('enroll')) return 'school';
    return 'task_alt';
}

function setGpsStatusText(text) {
    const el = document.getElementById('gpsStatus');
    if (!el) return;
    const pill = el.querySelector('.pill-text');
    if (pill) pill.innerText = text;
    else el.innerText = text;
}

function updateStatusHero(roadmapData) {
    const titleEl = document.getElementById('statusHeroTitle');
    const badgeEl = document.getElementById('statusHeroBadge');
    const badgeTextEl = document.getElementById('statusHeroBadgeText');
    if (!titleEl || !roadmapData) return;
    const trans = uiTranslations[currentLang] || {};
    const prog = roadmapData.progress || {};
    const remaining = Math.max(0, (prog.total || 0) - (prog.completed || 0));
    titleEl.innerText = remaining === 1
        ? (trans.statusHeroTasksOne || 'Today you have 1 task')
        : (trans.statusHeroTasks || 'Today you have {n} tasks').replace('{n}', String(remaining));

    const next = roadmapData.next_tasks && roadmapData.next_tasks[0];
    if (badgeEl && badgeTextEl && next) {
        badgeEl.classList.remove('hidden');
        badgeTextEl.innerText = next.title;
    } else if (badgeEl) {
        badgeEl.classList.add('hidden');
    }

    // Show AI mission statement as subtitle if available
    const aiP = roadmapData.ai_personalization;
    const missionEl = document.getElementById('statusHeroMission');
    if (missionEl) {
        if (aiP && aiP.mission) {
            missionEl.textContent = aiP.mission;
            missionEl.classList.remove('hidden');
        } else {
            missionEl.classList.add('hidden');
        }
    }
}

function renderJourneySteps(roadmapData) {
    const container = document.getElementById('journeySteps');
    if (!container || !roadmapData) return;

    const slots = [];
    const completedSet = new Set(completedTasks);
    for (const phase of roadmapData.phases || []) {
        for (const task of phase.tasks || []) {
            if (task.kind === 'endpoint' || task.kind === 'milestone') continue;
            slots.push(task);
        }
    }

    const visible = [];
    const activeIdx = slots.findIndex(t => t.state === 'available');
    const start = Math.max(0, activeIdx === -1 ? slots.length - 4 : activeIdx - 1);
    for (let i = start; i < slots.length && visible.length < 4; i++) {
        visible.push(slots[i]);
    }
    while (visible.length < 4 && visible.length < slots.length) {
        const prev = slots[slots.indexOf(visible[0]) - 1];
        if (prev) visible.unshift(prev);
        else break;
    }

    container.innerHTML = visible.map((task) => {
        const isDone = task.state === 'completed' || completedSet.has(task.id);
        const isActive = task.state === 'available';
        const cls = `journey-step${isDone ? ' done' : ''}${isActive ? ' active' : ''}`;
        const label = (task.title || '').replace(/<[^>]+>/g, '').slice(0, 14);
        const icon = taskJourneyIcon(task.id);
        const check = isDone
            ? `<span class="journey-step-check"><span class="material-symbols-outlined">check</span></span>`
            : '';
        return `<button type="button" class="${cls}" onclick="selectRoadmapTask('${task.id}')" title="${escapeHtml(task.title || '')}">
            <span class="journey-step-circle">
                <span class="material-symbols-outlined">${icon}</span>
                ${check}
            </span>
            <span class="journey-step-label">${escapeHtml(label)}</span>
        </button>`;
    }).join('');
}

function syncLangSelectors(lang) {
    document.querySelectorAll('#langSelector, #onboardLangSelector').forEach(el => {
        if (el) el.value = lang;
    });
}

async function initApp() {
    await loadTranslations(currentLang);
    
    syncLangSelectors(currentLang);
    applyTranslations(currentLang);
    initSchoolAutocomplete(currentLang);
    initLocationAutocomplete(currentLang);
    await loadOnboardTaskCheckboxes();
    await loadApiKeyStatus();
    await loadMapsKeyStatus();
    await loadServicesHealth();
    
    if (schoolInfo) {
        restoreOnboardFields();
        showWorkspace();
        clearStaleMockDecision();
        await fetchRoadmap();  // fetchRoadmap triggers fetchAgentDecision if no decision yet
        startLocationTracking();
        renderChatHistory();
    }
    startClock();
}

window.onload = initApp;

function showLoading() {
    const overlay = document.getElementById('globalLoadingOverlay');
    if (overlay) {
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    }
}

function cancelLoading() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    hideLoading();
}

function hideLoading() {
    const overlay = document.getElementById('globalLoadingOverlay');
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
    }
}

function startClock() {
    if (clockTimerId) clearInterval(clockTimerId);
    const tick = () => {
        const timeEl = document.getElementById('timeStatusTime');
        const dayEl = document.getElementById('timeStatusDay');
        if (!timeEl || !dayEl) return;
        const now = new Date();
        const timeStr = now.toLocaleTimeString(currentLang, { hour: '2-digit', minute: '2-digit' });
        const dayStr = now.toLocaleDateString(currentLang, { weekday: 'short' });
        if (timeEl.textContent !== timeStr) timeEl.textContent = timeStr;
        if (dayEl.textContent !== dayStr) dayEl.textContent = dayStr;
    };
    tick();
    clockTimerId = setInterval(tick, 1000);
}

window.addEventListener('beforeunload', () => {
    if (clockTimerId) clearInterval(clockTimerId);
    if (locationTimerId) clearInterval(locationTimerId);
});

async function changeLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('currentLang', lang);
    syncLangSelectors(lang);
    await loadTranslations(lang);
    applyTranslations(lang);
    if (document.getElementById('apiKeyStatusBadge')) {
        loadApiKeyStatus();
    }
    initSchoolAutocomplete(lang);
    initLocationAutocomplete(lang);
    await loadOnboardTaskCheckboxes();
    if (schoolInfo) {
        await fetchRoadmap();
        if (currentDecisionObj) {
            renderAgentDecision();
        }
    }
    if (chatHistory.length) {
        renderChatHistory();
    }
    if (isTaskSheetOpen() && selectedTaskId) {
        renderTaskDetail(selectedTaskId, true);
    }
    syncVoiceUi();
}

function updatePageTitle(lang) {
    const trans = uiTranslations[lang] || {};
    document.title = trans.appPageTitle || 'HARU | Japan Student Support';
}

function syncVoiceUi() {
    const trans = uiTranslations[currentLang] || {};
    const labelEl = document.getElementById('voiceSettingLabel');
    const btn = document.getElementById('voiceToggleBtn');
    if (labelEl) {
        labelEl.innerText = isVoiceEnabled
            ? (trans.voiceOn || 'Voice: ON')
            : (trans.voiceOff || 'Voice: OFF');
    }
    if (btn) {
        const icon = isVoiceEnabled ? 'volume_up' : 'volume_off';
        btn.innerHTML = `<span class="material-symbols-outlined">${icon}</span>`;
        btn.classList.toggle('voice-on', isVoiceEnabled);
        btn.setAttribute(
            'aria-label',
            isVoiceEnabled
                ? (trans.voiceOnAria || 'Voice on')
                : (trans.voiceOffAria || 'Voice off')
        );
    }
}

function applyTranslations(lang) {
    document.documentElement.lang = lang === 'zh-TW' ? 'zh-Hant' : lang;
    const trans = uiTranslations[lang];
    if (!trans) return;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (trans[key]) el.innerText = trans[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (trans[key]) el.placeholder = trans[key];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (trans[key]) el.title = trans[key];
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
        const key = el.getAttribute('data-i18n-aria-label');
        if (trans[key]) el.setAttribute('aria-label', trans[key]);
    });
    updatePageTitle(lang);
    syncVoiceUi();
    if (roadmapData) updateStatusHero(roadmapData);
}

function isStaleMockDecision(d) {
    if (!d) return true;
    if (d.source === 'mock') return true;
    const blob = JSON.stringify(d).toLowerCase();
    return blob.includes('mock') || blob.includes('\u30e2\u30c3\u30af') || blob.includes('\u6a21\u64ec');
}

function clearStaleMockDecision() {
    if (!isStaleMockDecision(currentDecisionObj)) return false;
    currentDecisionObj = null;
    lastAgentFingerprint = null;
    localStorage.removeItem('currentDecisionObj');
    return true;
}

function applyMissionFromRoadmap() {
    const focus = roadmapData?.next_tasks?.[0];
    const trans = uiTranslations[currentLang] || {};
    const titleEl = document.getElementById('currentFocusTitle');
    const speechEl = document.getElementById('agentSpeech');
    const hintEl = document.getElementById('upcomingHint');
    const faceEl = document.getElementById('agentFace');
    if (!titleEl) return false;

    // Prefer AI-generated personalization if available
    const aiP = roadmapData?.ai_personalization;
    if (aiP && (aiP.priority_message || aiP.mission)) {
        titleEl.innerText = focus?.title || (trans.allTasksDone || 'All tasks done');
        const greeting = aiP.agent_greeting ? `**${aiP.agent_greeting}**\n\n` : '';
        const body = greeting + (aiP.priority_message || aiP.mission || '');
        if (speechEl) speechEl.innerHTML = marked.parse(body);
        if (hintEl) {
            const next = roadmapData?.next_tasks?.[1];
            hintEl.innerText = next?.title || '';
        }
        if (faceEl) faceEl.innerText = agentFaces.guiding || 'H';
        document.getElementById('actionArea')?.classList.add('hidden');
        return true;
    }

    // Fallback: static roadmap data
    if (!focus) return false;
    titleEl.innerText = focus.title || '';
    const tips = (focus.tips || []).slice(0, 3).map(t => `\u2022 ${t}`).join('\n');
    const body = [focus.summary || '', tips].filter(Boolean).join('\n\n');
    if (speechEl) speechEl.innerHTML = marked.parse(body);
    if (hintEl) {
        const next = roadmapData?.next_tasks?.[1];
        hintEl.innerText = next?.title || '';
    }
    if (faceEl) faceEl.innerText = agentFaces.guiding || 'H';
    document.getElementById('actionArea')?.classList.add('hidden');
    return true;
}

function closeChatView(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    document.getElementById('talkHeader')?.classList.add('hidden');
}

function showWorkspace() {
    document.getElementById('onboardSection').classList.add('hidden');
    document.getElementById('workspaceSection').classList.remove('hidden');
    document.getElementById('bottomNav')?.classList.remove('hidden');
    const schoolTag = document.getElementById('schoolTag');
    schoolTag.innerText = schoolInfo.school_name;
    schoolTag.classList.remove('hidden');
    document.getElementById('voiceToggleBtn').classList.remove('hidden');
    switchView('stage');
}

function showOnboardEdit() {
    document.getElementById('onboardSection').classList.remove('hidden');
    document.getElementById('onboardSection').classList.add('onboard-edit-mode');
    document.getElementById('onboardCancelBtn')?.classList.remove('hidden');
    restoreOnboardFields();
    loadOnboardTaskCheckboxes();
}

function cancelOnboardEdit() {
    document.getElementById('onboardSection').classList.add('hidden');
    document.getElementById('onboardSection').classList.remove('onboard-edit-mode');
    document.getElementById('onboardCancelBtn')?.classList.add('hidden');
}

function switchView(viewName) {
    const views = { stage: 'view-stage', talk: 'view-talk', profile: 'view-profile' };
    Object.entries(views).forEach(([key, id]) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('active', key === viewName);
    });
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.toggle('on', btn.dataset.view === viewName);
    });
    if (viewName === 'talk') {
        document.getElementById('talkHeader')?.classList.remove('hidden');
        const chatWindow = document.getElementById('chatWindow');
        if (chatWindow) chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    if (viewName === 'profile') {
        loadApiKeyStatus();
        loadMapsKeyStatus();
        loadServicesHealth();
    }
}

function toggleRoadmapFullscreen(force) {
    const block = document.getElementById('roadmapBlock');
    const exitBtn = document.getElementById('roadmapFullscreenExitBtn');
    if (!block) return;
    const next = typeof force === 'boolean' ? force : !roadmapFullscreen;
    roadmapFullscreen = next;
    block.classList.toggle('is-fullscreen', next);
    document.body.classList.toggle('roadmap-fs-on', next);
    if (exitBtn) exitBtn.classList.toggle('hidden', !next);
    if (roadmapCanvas) {
        requestAnimationFrame(() => {
            roadmapCanvas.render();
            setTimeout(() => roadmapCanvas.render(), 120);
        });
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && roadmapFullscreen) toggleRoadmapFullscreen(false);
    if (e.key === 'Escape' && isTaskSheetOpen()) closeTaskSheet();
});

function showApiKeyFeedback(message, ok = true) {
    const el = document.getElementById('apiKeyFeedback');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden', 'ok', 'err');
    el.classList.add(ok ? 'ok' : 'err');
}

function hideApiKeyFeedback() {
    const el = document.getElementById('apiKeyFeedback');
    if (el) el.classList.add('hidden');
}

function setApiKeyBadge(state, icon, text) {
    const badge = document.getElementById('apiKeyStatusBadge');
    const iconEl = document.getElementById('apiKeyStatusIcon');
    const textEl = document.getElementById('apiKeyStatusText');
    if (!badge || !textEl) return;
    badge.className = `api-key-badge api-key-badge--${state}`;
    if (iconEl) iconEl.textContent = icon;
    textEl.textContent = text;
}

function apiKeyErrorMessage(trans, errorKind, fallback) {
    const map = {
        permission_denied: trans.apiKeyErrorPermissionDenied,
        invalid_key: trans.apiKeyErrorInvalid,
        quota: trans.apiKeyErrorQuota,
    };
    return map[errorKind] || fallback;
}

function extractApiError(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null) {
        return detail.message || JSON.stringify(detail);
    }
    return data?.message || fallback;
}

function mergeRoadmapCompletedFromResponse(roadmap) {
    if (!roadmap) return;
    const baseline = roadmap.baseline_completed || [];
    const user = roadmap.completed_tasks || [];
    completedTasks = Array.from(new Set([...user, ...baseline]));
    localStorage.setItem('completedTasks', JSON.stringify(completedTasks));
}

async function loadApiKeyStatus() {
    const trans = uiTranslations[currentLang] || {};
    const hintLine = document.getElementById('apiKeyHintLine');
    const input = document.getElementById('apiKeyInput');
    const clearBtn = document.getElementById('apiKeyClearBtn');
    hideApiKeyFeedback();
    try {
        const res = await fetch(`/api/settings/api-key?device_id=${encodeURIComponent(deviceId)}`);
        const data = await res.json();
        if (data.status !== 'success') return;

        if (data.mock_mode) {
            const mockLabel = data.user_saved
                ? (trans.apiKeyMockWithKey || trans.apiKeyMock || 'Mock mode — key saved but not used')
                : (trans.apiKeyMock || 'Mock mode (no API key needed)');
            setApiKeyBadge('mock', '', mockLabel);
            if (hintLine) hintLine.classList.add('hidden');
            if (input) input.placeholder = trans.apiKeyPlaceholder || '';
            if (clearBtn) clearBtn.disabled = !data.user_saved;
            return;
        }

        if (clearBtn) clearBtn.disabled = false;

        if (data.user_saved) {
            setApiKeyBadge(
                'ok',
                '',
                `${trans.apiKeySavedBadge || 'Saved on this device'}${data.hint ? ` · ${data.hint}` : ''}`
            );
            if (hintLine) {
                hintLine.textContent = `${trans.apiKeyMaskedLabel || 'Stored key'}: ${data.hint || '****'}`;
                hintLine.classList.remove('hidden');
            }
            if (input) {
                input.placeholder = trans.apiKeyReplacePlaceholder || 'Enter a new key to replace';
                input.value = '';
            }
        } else if (data.env_available) {
            setApiKeyBadge('warn', '', trans.apiKeyEnvOnly || 'Using server .env key (not saved in Profile)');
            if (hintLine) hintLine.classList.add('hidden');
            if (input) input.placeholder = trans.apiKeyPlaceholder || '';
        } else {
            setApiKeyBadge('missing', '', trans.apiKeyNotConfigured || 'Not configured — AI features need a key');
            if (hintLine) hintLine.classList.add('hidden');
            if (input) input.placeholder = trans.apiKeyPlaceholder || '';
        }
    } catch (e) {
        setApiKeyBadge('missing', '!', trans.apiKeyStatusError || 'Could not load API key status');
        if (hintLine) hintLine.classList.add('hidden');
    }
}

async function saveApiKey() {
    const input = document.getElementById('apiKeyInput');
    const saveBtn = document.getElementById('apiKeySaveBtn');
    const key = (input?.value || '').trim();
    const trans = uiTranslations[currentLang] || {};
    if (!key) {
        showApiKeyFeedback(trans.apiKeyEmpty || 'Please enter an API key', false);
        return;
    }
    if (saveBtn) { saveBtn.disabled = true; }
    hideApiKeyFeedback();
    try {
        const res = await fetch('/api/settings/api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, api_key: key, lang: currentLang }),
        });
        const data = await res.json();
        if (!res.ok) {
            const detail = data.detail || data.message || 'Failed to save API key';
            showApiKeyFeedback(typeof detail === 'string' ? detail : JSON.stringify(detail), false);
            return;
        }
        if (data.status === 'success') {
            if (input) input.value = '';
            await loadApiKeyStatus();
            await loadServicesHealth();
            const modelNote = data.verified_model ? ` (${data.verified_model})` : '';
            showApiKeyFeedback((trans.apiKeySavedVerified || 'Saved and verified') + modelNote, true);
        }
    } catch (e) {
        showApiKeyFeedback(trans.errorConnection || 'Connection error', false);
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function testApiKey() {
    const input = document.getElementById('apiKeyInput');
    const testBtn = document.getElementById('apiKeyTestBtn');
    const trans = uiTranslations[currentLang] || {};
    const key = (input?.value || '').trim();
    if (testBtn) testBtn.disabled = true;
    hideApiKeyFeedback();
    try {
        const res = await fetch('/api/settings/api-key/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                api_key: key,
                lang: currentLang,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            const detail = data.detail;
            let message = 'Test failed';
            if (typeof detail === 'object' && detail !== null) {
                message = apiKeyErrorMessage(trans, detail.error_kind, detail.message || message);
            } else if (typeof detail === 'string') {
                message = detail;
            }
            showApiKeyFeedback(message, false);
            return;
        }
        showApiKeyFeedback(
            `${trans.apiKeyTestOk || 'Connection OK'}${data.verified_model ? ` (${data.verified_model})` : ''}${data.hint ? ` · ${data.hint}` : ''}`,
            true
        );
    } catch (e) {
        showApiKeyFeedback(trans.errorConnection || 'Connection error', false);
    } finally {
        if (testBtn) testBtn.disabled = false;
    }
}

async function clearApiKey() {
    const trans = uiTranslations[currentLang] || {};
    if (!confirm(trans.apiKeyClearConfirm || 'Remove saved API key from this device?')) return;
    try {
        const res = await fetch(`/api/settings/api-key?device_id=${encodeURIComponent(deviceId)}`, {
            method: 'DELETE',
        });
        const data = await res.json();
        if (data.status === 'success') {
            const input = document.getElementById('apiKeyInput');
            if (input) input.value = '';
            await loadApiKeyStatus();
            showApiKeyFeedback(trans.apiKeyCleared || 'Saved API key removed from this device', true);
        }
    } catch (e) {
        showApiKeyFeedback(trans.errorConnection || 'Connection error', false);
    }
}

function setMapsKeyBadge(state, icon, text) {
    const badge = document.getElementById('mapsKeyStatusBadge');
    const iconEl = document.getElementById('mapsKeyStatusIcon');
    const textEl = document.getElementById('mapsKeyStatusText');
    if (!badge || !textEl) return;
    badge.className = `api-key-badge api-key-badge--${state}`;
    if (iconEl) iconEl.textContent = icon;
    textEl.textContent = text;
}

function showMapsKeyFeedback(message, ok) {
    const el = document.getElementById('mapsKeyFeedback');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden', 'profile-api-feedback--ok', 'profile-api-feedback--err');
    el.classList.add(ok ? 'profile-api-feedback--ok' : 'profile-api-feedback--err');
}

function hideMapsKeyFeedback() {
    document.getElementById('mapsKeyFeedback')?.classList.add('hidden');
}

async function loadMapsKeyStatus() {
    const trans = uiTranslations[currentLang] || {};
    const hintLine = document.getElementById('mapsKeyHintLine');
    const input = document.getElementById('mapsKeyInput');
    const clearBtn = document.getElementById('mapsKeyClearBtn');
    hideMapsKeyFeedback();
    try {
        const res = await fetch(`/api/settings/maps-key?device_id=${encodeURIComponent(deviceId)}`);
        const data = await res.json();
        if (data.status !== 'success') return;
        if (clearBtn) clearBtn.disabled = false;
        if (data.user_saved) {
            setMapsKeyBadge('ok', '', `${trans.mapsKeySavedBadge || 'Saved on this device'}${data.hint ? ` · ${data.hint}` : ''}`);
            if (hintLine) {
                hintLine.textContent = `${trans.mapsKeyMaskedLabel || 'Stored key'}: ${data.hint || '****'}`;
                hintLine.classList.remove('hidden');
            }
            if (input) input.placeholder = trans.mapsKeyReplacePlaceholder || 'Enter a new key to replace';
        } else if (data.env_available) {
            setMapsKeyBadge('warn', '', trans.mapsKeyEnvOnly || 'Using server .env key');
            if (hintLine) hintLine.classList.add('hidden');
        } else {
            setMapsKeyBadge('missing', '', trans.mapsKeyNotConfigured || 'Optional — basic maps work without a key');
            if (hintLine) hintLine.classList.add('hidden');
            if (input) input.placeholder = trans.mapsKeyPlaceholder || '';
        }
    } catch (e) {
        setMapsKeyBadge('missing', '!', trans.mapsKeyStatusError || 'Could not load Maps key status');
    }
}

async function saveMapsKey() {
    const input = document.getElementById('mapsKeyInput');
    const saveBtn = document.getElementById('mapsKeySaveBtn');
    const key = (input?.value || '').trim();
    const trans = uiTranslations[currentLang] || {};
    if (!key) {
        showMapsKeyFeedback(trans.mapsKeyEmpty || 'Please enter a Maps API key', false);
        return;
    }
    if (saveBtn) saveBtn.disabled = true;
    hideMapsKeyFeedback();
    try {
        const res = await fetch('/api/settings/maps-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, api_key: key }),
        });
        const data = await res.json();
        if (!res.ok) {
            showMapsKeyFeedback(extractApiError(data, 'Failed to save Maps key'), false);
            return;
        }
        if (input) input.value = '';
        await loadMapsKeyStatus();
        await loadServicesHealth();
        showMapsKeyFeedback(trans.mapsKeySaved || 'Maps API key saved', true);
    } catch (e) {
        showMapsKeyFeedback(trans.errorConnection || 'Connection error', false);
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

async function testMapsKey() {
    const input = document.getElementById('mapsKeyInput');
    const testBtn = document.getElementById('mapsKeyTestBtn');
    const trans = uiTranslations[currentLang] || {};
    const key = (input?.value || '').trim();
    if (testBtn) testBtn.disabled = true;
    hideMapsKeyFeedback();
    try {
        const res = await fetch('/api/settings/maps-key/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, api_key: key || undefined }),
        });
        const data = await res.json();
        if (!res.ok) {
            showMapsKeyFeedback(extractApiError(data, 'Test failed'), false);
            return;
        }
        showMapsKeyFeedback(`${trans.mapsKeyTestOk || 'Maps key OK'}${data.hint ? ` · ${data.hint}` : ''}`, true);
    } catch (e) {
        showMapsKeyFeedback(trans.errorConnection || 'Connection error', false);
    } finally {
        if (testBtn) testBtn.disabled = false;
    }
}

async function clearMapsKey() {
    const trans = uiTranslations[currentLang] || {};
    if (!confirm(trans.mapsKeyClearConfirm || 'Remove saved Maps API key from this device?')) return;
    try {
        const res = await fetch(`/api/settings/maps-key?device_id=${encodeURIComponent(deviceId)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('mapsKeyInput').value = '';
            await loadMapsKeyStatus();
            await loadServicesHealth();
            showMapsKeyFeedback(trans.mapsKeyCleared || 'Maps API key removed', true);
        }
    } catch (e) {
        showMapsKeyFeedback(trans.errorConnection || 'Connection error', false);
    }
}

async function loadServicesHealth() {
    const el = document.getElementById('servicesHealthList');
    if (!el) return;
    const trans = uiTranslations[currentLang] || {};
    try {
        const res = await fetch(`/api/settings/services/health?device_id=${encodeURIComponent(deviceId)}`);
        const data = await res.json();
        if (data.status !== 'success') return;
        const row = (label, svc) => {
            const ok = svc.available;
            const note = svc.mock_mode
                ? (trans.serviceMock || 'Mock')
                : (ok ? (trans.serviceReady || 'Ready') : (trans.serviceUnavailable || 'Unavailable'));
            return `<div class="service-health-row"><span>${escapeHtml(label)}</span><span class="service-health-badge service-health-badge--${ok ? 'ok' : 'off'}">${escapeHtml(note)}</span></div>`;
        };
        el.innerHTML = [
            row(trans.serviceGemini || 'Gemini AI', data.gemini || {}),
            row(trans.serviceMaps || 'Google Maps', data.maps || {}),
            row(trans.serviceTts || 'Text-to-Speech', data.tts || {}),
            row(trans.serviceStt || 'Speech-to-Text', data.stt || {}),
        ].join('');
    } catch (e) {
        el.innerHTML = `<p class="profile-api-hint">${escapeHtml(trans.apiKeyStatusError || 'Could not load status')}</p>`;
    }
}

function isTaskSheetOpen() {
    return !document.getElementById('taskSheet')?.classList.contains('hidden');
}

function openTaskSheet() {
    document.getElementById('taskSheetBackdrop')?.classList.remove('hidden');
    document.getElementById('taskSheet')?.classList.remove('hidden');
    document.body.classList.add('sheet-open');
}

function closeTaskSheet() {
    document.getElementById('taskSheetBackdrop')?.classList.add('hidden');
    document.getElementById('taskSheet')?.classList.add('hidden');
    document.body.classList.remove('sheet-open');
}

function openMapSheet() {
    document.getElementById('mapSheetBackdrop')?.classList.remove('hidden');
    document.getElementById('mapSheet')?.classList.remove('hidden');
}

function openMapWithQuery(rawQuery) {
    const query = (rawQuery || '').trim();
    if (!query) return;
    const lat = currentGPS.latitude;
    const lon = currentGPS.longitude;
    const params = new URLSearchParams({ query, device_id: deviceId });
    if (lat != null) params.set('latitude', String(lat));
    if (lon != null) params.set('longitude', String(lon));
    const applySrc = (src) => {
        const inlineFrame = document.getElementById('inlineMapFrame');
        const mapFrame = document.getElementById('dynamicMapFrame');
        const sheetFrame = document.getElementById('mapSheetFrame');
        if (inlineFrame) inlineFrame.src = src;
        if (mapFrame) mapFrame.src = src;
        if (sheetFrame) sheetFrame.src = src;
        const panel = document.getElementById('inlineMapPanel');
        panel?.classList.remove('hidden');
        panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        switchView('stage');
        openMapSheet();
    };
    fetch(`/api/maps/embed-url?${params.toString()}`)
        .then((res) => res.json())
        .then((data) => {
            applySrc(data.embed_url || `https://maps.google.com/maps?q=${encodeURIComponent(query)}&z=15&output=embed`);
        })
        .catch(() => {
            applySrc(`https://maps.google.com/maps?q=${encodeURIComponent(query)}&z=15&output=embed`);
        });
}

function closeMapSheet() {
    document.getElementById('mapSheetBackdrop')?.classList.add('hidden');
    document.getElementById('mapSheet')?.classList.add('hidden');
}

function openScannerSheet() {
    document.getElementById('scannerSheetBackdrop')?.classList.remove('hidden');
    document.getElementById('scannerSheet')?.classList.remove('hidden');
}

function closeScannerSheet() {
    document.getElementById('scannerSheetBackdrop')?.classList.add('hidden');
    document.getElementById('scannerSheet')?.classList.add('hidden');
}

function scrollToTaskDetail() {
    const taskId = selectedTaskId || roadmapData?.next_tasks?.[0]?.id;
    if (!taskId) return;
    selectRoadmapTask(taskId, true);
}

function openCurrentMission() {
    scrollToTaskDetail();
}

function updateMissionCard() {
    const titleEl = document.getElementById('missionCardTitle');
    const summaryEl = document.getElementById('missionCardSummary');
    if (!titleEl || !summaryEl || !roadmapData) return;
    const task = selectedTaskId ? findTaskInRoadmap(selectedTaskId) : roadmapData.next_tasks?.[0];
    if (task) {
        titleEl.innerText = task.title;
        summaryEl.innerText = task.summary || '';
    }
}

window.switchView = switchView;
window.toggleRoadmapFullscreen = toggleRoadmapFullscreen;
window.saveApiKey = saveApiKey;
window.testApiKey = testApiKey;
window.clearApiKey = clearApiKey;
window.saveMapsKey = saveMapsKey;
window.testMapsKey = testMapsKey;
window.clearMapsKey = clearMapsKey;
window.selectRoadmapTask = selectRoadmapTask;
window.openTaskSheet = openTaskSheet;
window.closeTaskSheet = closeTaskSheet;
window.openMapSheet = openMapSheet;
window.openMapWithQuery = openMapWithQuery;
window.closeMapSheet = closeMapSheet;
window.openScannerSheet = openScannerSheet;
window.closeScannerSheet = closeScannerSheet;
window.showOnboardEdit = showOnboardEdit;
window.cancelOnboardEdit = cancelOnboardEdit;
window.openCurrentMission = openCurrentMission;
window.scrollToTaskDetail = scrollToTaskDetail;
window.closeChatView = closeChatView;
window.viewRoadmapPdf = viewRoadmapPdf;
window.closePdfViewer = closePdfViewer;
window.downloadCurrentPdf = downloadCurrentPdf;

function toggleVoice() {
    isVoiceEnabled = !isVoiceEnabled;
    syncVoiceUi();
}

async function speakText(text) {
    if (!isVoiceEnabled) return;
    try {
        const res = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, lang: currentLang })
        });
        const data = await res.json();
        if (data.status === 'success' && data.audio) {
            const snd = new Audio("data:audio/mp3;base64," + data.audio);
            snd.play();
        }
    } catch (e) {
        console.error("TTS failed", e);
    }
}

function getOnboardProfile() {
    return {
        housing_type: document.getElementById('housingType')?.value || schoolInfo?.housing_type || 'dorm',
        school_type: document.getElementById('schoolType')?.value || schoolInfo?.school_type || 'language_school',
        part_time_plan: document.getElementById('partTimePlan')?.value || schoolInfo?.part_time_plan || 'no',
        sim_at_airport: document.getElementById('simAtAirport')?.checked || schoolInfo?.sim_at_airport || false,
        already_exchanged: document.getElementById('alreadyExchanged')?.checked || schoolInfo?.already_exchanged || false,
        permit_obtained: document.getElementById('permitObtained')?.checked || schoolInfo?.permit_obtained || false,
        has_residence_card: document.getElementById('hasResidenceCard')?.checked || schoolInfo?.has_residence_card || false,
    };
}

function onPartTimePlanChange() {
    const plan = document.getElementById('partTimePlan')?.value || 'no';
    const permitField = document.getElementById('permitObtainedField');
    if (permitField) {
        permitField.style.display = (plan === 'yes' || plan === 'later') ? '' : 'none';
    }
    loadOnboardTaskCheckboxes();
}

async function loadOnboardTaskCheckboxes() {
    const container = document.getElementById('onboardTaskList');
    if (!container) return;
    const profile = getOnboardProfile();
    const qs = new URLSearchParams({
        housing_type: profile.housing_type,
        part_time_plan: profile.part_time_plan,
        school_type: profile.school_type,
        lang: currentLang,
        sim_at_airport: profile.sim_at_airport ? 'true' : 'false',
        already_exchanged: profile.already_exchanged ? 'true' : 'false',
    });
    try {
        const res = await fetch(`/api/roadmap/schema?${qs}`);
        const data = await res.json();
        if (data.status !== 'success') return;
        onboardTaskSchema = data.tasks || [];
        // task_immigration is controlled by the hasResidenceCard checkbox above,
        // so exclude it from the dynamic list to avoid showing it twice.
        const EXCLUDED_FROM_DYNAMIC_LIST = new Set(['task_immigration']);
        const checked = new Set(completedTasks);
        container.innerHTML = onboardTaskSchema
            .filter(t => !EXCLUDED_FROM_DYNAMIC_LIST.has(t.id))
            .map(t => `
            <label class="onboard-task-item check-container">
                <input type="checkbox" class="onboard-task-chk" data-task-id="${t.id}" ${checked.has(t.id) ? 'checked' : ''}>
                <span>${t.title}</span>
            </label>
        `).join('');
    } catch (e) {
        console.error('Failed to load onboard tasks', e);
    }
}

function restoreOnboardFields() {
    if (!schoolInfo) return;
    const setVal = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setSchoolFieldValue(schoolInfo.school_name);
    setVal('arrivalDate', schoolInfo.arrival_date);
    setLocationFieldValue(schoolInfo.location);
    setVal('japaneseLevel', schoolInfo.japanese_level);
    setChk('hasResidenceCard', schoolInfo.has_residence_card);
    setVal('housingType', schoolInfo.housing_type || 'dorm');
    setVal('schoolType', schoolInfo.school_type || 'language_school');
    setVal('partTimePlan', schoolInfo.part_time_plan || 'no');
    setChk('simAtAirport', schoolInfo.sim_at_airport);
    setChk('alreadyExchanged', schoolInfo.already_exchanged);
    setChk('permitObtained', schoolInfo.permit_obtained);
    onPartTimePlanChange();
}

async function fetchRoadmap() {
    if (!schoolInfo) return;
    try {
        const res = await fetch('/api/roadmap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                lang: currentLang,
                branch_choices: branchChoices,
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            roadmapData = data.roadmap;
            if (data.roadmap.branch_choices) {
                branchChoices = data.roadmap.branch_choices;
                localStorage.setItem('branchChoices', JSON.stringify(branchChoices));
            }
            mergeRoadmapCompletedFromResponse(data.roadmap);
            renderRoadmap();
            // Update hero mission if AI personalization arrived
            if (data.roadmap.ai_personalization) {
                updateStatusHero(data.roadmap);
                if (!currentDecisionObj) {
                    applyMissionFromRoadmap();
                }
            }
            if (!currentDecisionObj) {
                fetchAgentDecision(null, null, true);
            }
        }
    } catch (e) {
        console.error('Failed to fetch roadmap', e);
    }
}

function findTaskInRoadmap(taskId) {
    if (!roadmapData) return null;
    for (const phase of roadmapData.phases) {
        for (const task of phase.tasks) {
            if (task.id === taskId) return task;
        }
    }
    return null;
}

function ensureTaskSelected(taskId) {
    selectedTaskId = taskId;
    if (!roadmapData) return;
    for (const phase of roadmapData.phases) {
        if (phase.tasks.some((t) => t.id === taskId)) {
            selectedPhaseId = phase.id;
            break;
        }
    }
}

function renderRoadmap(skipTaskDetail = false) {
    if (!roadmapData) return;
    const trans = uiTranslations[currentLang] || {};
    const prog = roadmapData.progress;
    const progText = (trans.roadmapProgress || 'Progress {done}/{total}')
        .replace('{done}', prog.completed).replace('{total}', prog.total);
    document.getElementById('roadmapProgressText').innerText = progText;
    document.getElementById('roadmapProgressBar').style.width = `${prog.percent}%`;
    const ringEl = document.getElementById('roadmapProgressRing');
    const pctEl = document.getElementById('roadmapProgressPercent');
    if (ringEl) ringEl.style.setProperty('--progress', prog.percent);
    if (pctEl) pctEl.innerText = String(prog.percent);
    const routePrefix = trans.routeLabel || 'Route';
    document.getElementById('roadmapRouteLabel').innerText = `${routePrefix}: ${roadmapData.route.label}`;

    const branchSummaryEl = document.getElementById('roadmapBranchSummary');
    if (branchSummaryEl) {
        const summary = roadmapData.branch_summary || [];
        if (summary.length) {
            branchSummaryEl.classList.remove('hidden');
            branchSummaryEl.innerHTML = `<span style="color:var(--accent)">${trans.branchPathLabel || 'Branch path'}:</span> ` +
                summary.map(s => escapeHtml(s.label)).join(' → ');
        } else {
            branchSummaryEl.classList.add('hidden');
            branchSummaryEl.innerHTML = '';
        }
    }

    updateStatusHero(roadmapData);
    renderJourneySteps(roadmapData);

    // Auto-select phase only when nothing is selected yet.
    // Once the user picks a tab (selectedPhaseId is set), never override it here.
    if (!selectedPhaseId || !roadmapData.phases.find(p => p.id === selectedPhaseId && p.tasks.length)) {
        const firstActive = roadmapData.phases.find((p) =>
            p.tasks.some((t) => t.state === 'available' || t.state === 'locked')
        );
        const firstWithTasks = firstActive || roadmapData.phases.find((p) => p.tasks.length);
        if (firstWithTasks) selectedPhaseId = firstWithTasks.id;
    }

    const tabsEl = document.getElementById('roadmapPhaseTabs');
    tabsEl.innerHTML = '';
    roadmapData.phases.forEach(phase => {
        if (!phase.tasks.length) return;
        const btn = document.createElement('button');
        const isActive = selectedPhaseId === phase.id;
        btn.className = `roadmap-phase-tab${isActive ? ' active' : ''}`;
        btn.innerText = phase.title;
        btn.onclick = () => {
            selectedPhaseId = phase.id;
            _suppressFocusScroll = true;  // don't let next renderRoadmap scroll back
            // Only update tab highlight and scroll — do NOT call renderRoadmap()
            // which would trigger ensureTaskSelected and pull the phase back.
            document.querySelectorAll('.roadmap-phase-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (roadmapCanvas) roadmapCanvas.scrollToPhase(phase.id);
        };
        tabsEl.appendChild(btn);
    });

    const phase = roadmapData.phases.find(p => p.id === selectedPhaseId) || roadmapData.phases[0];
    const canvasEl = document.getElementById('roadmapCanvas');
    const wrapEl = document.getElementById('roadmapCanvasWrap');
    if (canvasEl && wrapEl && window.RoadmapCanvas) {
        if (!roadmapCanvas) {
            roadmapCanvas = new RoadmapCanvas(canvasEl, wrapEl);
        }
        roadmapCanvas.setData(
            roadmapData,
            selectedTaskId,
            currentLang,
            roadmapData?.next_tasks?.[0]?.id || null,
        );
        // Auto-scroll to current focus task, unless the user just clicked a phase tab
        if (roadmapData?.next_tasks?.[0]?.id && !_suppressFocusScroll) {
            setTimeout(() => roadmapCanvas.scrollToCurrentFocus(), 200);
        }
        _suppressFocusScroll = false;  // reset after each render
    }
    if (!phase) return;

    if (!skipTaskDetail) {
        if (!selectedTaskId && roadmapData.next_tasks?.[0]) {
            // Only auto-follow the focus task's phase if selectedPhaseId hasn't been set yet
            if (!selectedPhaseId) {
                ensureTaskSelected(roadmapData.next_tasks[0].id);
            }
        }
        if (selectedTaskId) {
            renderTaskDetail(selectedTaskId, isTaskSheetOpen());
        }
    }

    if (currentDecisionObj && roadmapData.next_tasks && roadmapData.next_tasks[0] && isStaleMockDecision(currentDecisionObj)) {
        applyMissionFromRoadmap();
    }

    if (selectedTaskId) {
        refreshComposerChips(selectedTaskId);
    }
    updateMissionCard();
}

function selectRoadmapTask(taskId, openSheet = true) {
    ensureTaskSelected(taskId);  // also updates selectedPhaseId to follow the task
    renderRoadmap(true);
    renderTaskDetail(taskId, openSheet);
    refreshComposerChips(taskId);
}

function renderTaskDetail(taskId, openSheet = false) {
    const task = findTaskInRoadmap(taskId);
    const hint = document.getElementById('roadmapSelectHint');
    const content = document.getElementById('roadmapDetailContent');
    if (!task) {
        hint.classList.remove('hidden');
        content.classList.add('hidden');
        if (openSheet) closeTaskSheet();
        return;
    }
    hint.classList.add('hidden');
    content.classList.remove('hidden');
    const trans = uiTranslations[currentLang] || {};
    const titleText = task.title + (task.kind === 'awareness' ? ` · ${trans.awarenessBadge || 'Info'}` : '');

    const sheetTitle = document.getElementById('taskSheetTitle');
    if (sheetTitle) sheetTitle.innerText = titleText;
    document.getElementById('roadmapDetailTitle').innerText = titleText;
    document.getElementById('roadmapDetailSummary').innerText = task.summary || '';

    let meta = '';
    if (task.duration_min) meta += `${trans.durationLabel || 'Time'}: ${task.duration_min} ${trans.minutesLabel || 'min'}`;
    if (task.deadline_days_after_arrival) {
        const dl = (trans.daysAfterArrival || 'Within {n} days').replace('{n}', task.deadline_days_after_arrival);
        meta += (meta ? ' · ' : '') + dl;
    }
    document.getElementById('roadmapDetailMeta').innerText = meta;

    const lockEl = document.getElementById('roadmapDetailLock');
    if (task.state === 'locked' && task.lock_reason) {
        lockEl.innerText = task.lock_reason;
        lockEl.classList.remove('hidden');
    } else {
        lockEl.classList.add('hidden');
    }

    const docsEl = document.getElementById('roadmapDetailDocs');
    if (task.documents && task.documents.length) {
        docsEl.innerHTML = `<div class="detail-label">${trans.documentsLabel || 'Documents'}</div>` +
            task.documents.map(d => `<label class="check-list" style="margin:0"><input type="checkbox" disabled> ${d.label}</label>`).join('');
    } else {
        docsEl.innerHTML = '';
    }

    const tipsEl = document.getElementById('roadmapDetailTips');
    tipsEl.innerHTML = (task.tips || []).map(t => `<li>${t}</li>`).join('');

    // Show AI-generated steps if present on the task (from ai_personalization overlay)
    const aiStepsEl = document.getElementById('roadmapDetailAiSteps');
    if (aiStepsEl) {
        const steps = task.ai_steps || [];
        if (steps.length) {
            const trans2 = uiTranslations[currentLang] || {};
            aiStepsEl.classList.remove('hidden');
            aiStepsEl.innerHTML = `<div class="detail-label ai-steps-label">
                <span class="material-symbols-outlined" style="font-size:14px;vertical-align:middle">auto_awesome</span>
                ${trans2.aiStepsLabel || 'AI-suggested steps'}
            </div>` +
                `<ol class="ai-steps-list">` +
                steps.map(s => `<li>${escapeHtml(s)}</li>`).join('') +
                `</ol>`;
        } else {
            aiStepsEl.classList.add('hidden');
            aiStepsEl.innerHTML = '';
        }
    }

    const linksEl = document.getElementById('roadmapDetailLinks');
    if (linksEl) {
        renderOfficialLinks(task.official_links || [], linksEl);
    }

    const guidesEl = document.getElementById('roadmapDetailGuides');
    if (guidesEl && typeof loadGuidesForTask === 'function') {
        loadGuidesForTask(taskId, guidesEl);
    }

    renderBranchSection(task);
    renderTaskDetailActions(taskId);

    const expandEl = document.getElementById('roadmapDetailExpanded');
    const persEl = document.getElementById('roadmapDetailPersonalized');
    if (expandEl) {
        expandEl.classList.add('hidden');
        expandEl.innerHTML = '';
    }
    if (persEl) {
        persEl.classList.add('hidden');
        persEl.innerHTML = '';
    }
    if (taskExpansionCache[taskId]) {
        showExpansionPanel(taskExpansionCache[taskId]);
    }
    if (taskPersonalizedCache[taskId]) {
        showPersonalizedPanel(taskPersonalizedCache[taskId]);
    }

    const completeBtn = document.getElementById('roadmapCompleteBtn');
    const isAwareness = task.kind === 'awareness';
    if (isAwareness) {
        completeBtn.classList.add('hidden');
    } else if (task.state === 'available') {
        completeBtn.classList.remove('hidden');
        completeBtn.disabled = false;
        completeBtn.innerText = trans.markComplete || 'Mark complete';
    } else if (task.state === 'completed') {
        completeBtn.classList.remove('hidden');
        completeBtn.disabled = true;
        completeBtn.innerText = trans.markComplete || 'Mark complete';
    } else {
        completeBtn.classList.add('hidden');
    }
    if (openSheet) openTaskSheet();
}

function renderBranchSection(task) {
    const el = document.getElementById('roadmapDetailBranches');
    if (!el) return;
    const trans = uiTranslations[currentLang] || {};
    const bp = task.branch_point;
    if (!bp) {
        el.classList.add('hidden');
        el.innerHTML = '';
        return;
    }
    el.classList.remove('hidden');
    if (bp.selected) {
        const chosen = (bp.choices || []).find(c => c.id === bp.selected);
        el.innerHTML = `<div class="branch-block">
            <div class="branch-block-title">${trans.branchSelectedLabel || 'Selected branch'}</div>
            <div style="font-size:0.62rem;color:var(--base-light)">${escapeHtml(chosen?.label || bp.selected)}</div>
        </div>`;
        return;
    }
    el.innerHTML = `<div class="branch-block">
        <div class="branch-block-title">${escapeHtml(bp.prompt || '')}</div>
        <div class="branch-choice-list"></div>
    </div>`;
    const list = el.querySelector('.branch-choice-list');
    (bp.choices || []).forEach(choice => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'branch-choice-btn';
        btn.innerHTML = `<strong>${escapeHtml(choice.label)}</strong>
            ${choice.description ? `<span style="font-size:0.55rem;opacity:0.75">${escapeHtml(choice.description)}</span>` : ''}`;
        btn.onclick = () => selectBranchChoice(bp.id, choice.id);
        list.appendChild(btn);
    });
}

function renderTaskDetailActions(taskId) {
    const actionsEl = document.getElementById('roadmapDetailActions');
    if (!actionsEl) return;
    const trans = uiTranslations[currentLang] || {};
    actionsEl.classList.remove('hidden');
    const expandBtn = document.getElementById('roadmapExpandBtn');
    const persBtn = document.getElementById('roadmapPersonalizeBtn');
    if (expandBtn) expandBtn.innerText = trans.expandTaskBtn || 'Expand details';
    if (persBtn) persBtn.innerText = trans.personalizeTaskBtn || 'AI personalized steps';
}

async function selectBranchChoice(branchId, choiceId) {
    showLoading();
    try {
        const res = await fetch('/api/roadmap/branch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                branch_id: branchId,
                choice_id: choiceId,
                branch_choices: branchChoices,
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                lang: currentLang,
            }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            branchChoices = data.branch_choices || branchChoices;
            localStorage.setItem('branchChoices', JSON.stringify(branchChoices));
            roadmapData = data.roadmap;
            if (data.completed_tasks) {
                completedTasks = data.completed_tasks;
                localStorage.setItem('completedTasks', JSON.stringify(completedTasks));
            }
            taskExpansionCache = {};
            renderRoadmap();
        }
    } catch (e) {
        console.error('Branch select failed', e);
    } finally {
        hideLoading();
    }
}

function showExpansionPanel(expansion) {
    const el = document.getElementById('roadmapDetailExpanded');
    if (!el || !expansion) return;
    const trans = uiTranslations[currentLang] || {};
    el.classList.remove('hidden');
    const sections = (expansion.sections || []).map(sec => `
        <div class="mb-2">
            <div class="detail-section-heading">${escapeHtml(sec.heading || '')}</div>
            <div class="detail-section-body">${escapeHtml(sec.body || '')}</div>
        </div>`).join('');
    el.innerHTML = `<div class="detail-panel-block">
        <div class="detail-panel-title">${trans.expandedDetailTitle || 'Detailed guide'}</div>
        ${sections}
    </div>`;
}

function showPersonalizedPanel(personalized) {
    const el = document.getElementById('roadmapDetailPersonalized');
    if (!el || !personalized) return;
    const trans = uiTranslations[currentLang] || {};
    el.classList.remove('hidden');
    const mockTag = personalized.mock ? `<span style="font-size:0.5rem;color:var(--accent)">${trans.mockBadge || 'Mock'}</span>` : '';
    el.innerHTML = `<div class="detail-panel-block">
        <div class="detail-panel-title">${trans.personalizedPlanTitle || 'Your personalized plan'} ${mockTag}</div>
        <div class="detail-section-body markdown-content" id="roadmapPersonalizedContent"></div>
    </div>`;
    const contentEl = document.getElementById('roadmapPersonalizedContent');
    if (contentEl) contentEl.innerHTML = marked.parse(personalized.content || '');
}

async function expandTaskDetail() {
    if (!selectedTaskId || !schoolInfo) return;
    const trans = uiTranslations[currentLang] || {};
    const btn = document.getElementById('roadmapExpandBtn');
    if (btn) { btn.disabled = true; btn.innerText = trans.expandingLabel || 'Loading...'; }
    try {
        const res = await fetch('/api/roadmap/task/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: selectedTaskId,
                school_info: schoolInfo,
                branch_choices: branchChoices,
                lang: currentLang,
            }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            taskExpansionCache[selectedTaskId] = data.expansion;
            showExpansionPanel(data.expansion);
        }
    } catch (e) {
        console.error('Expand failed', e);
    } finally {
        if (btn) { btn.disabled = false; btn.innerText = trans.expandTaskBtn || 'Expand details'; }
    }
}

async function personalizeTaskDetail() {
    if (!selectedTaskId || !schoolInfo) return;
    const trans = uiTranslations[currentLang] || {};
    const btn = document.getElementById('roadmapPersonalizeBtn');
    if (btn) { btn.disabled = true; btn.innerText = trans.personalizingLabel || 'Generating...'; }
    showLoading();
    try {
        const res = await fetch('/api/roadmap/task/personalize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: selectedTaskId,
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                branch_choices: branchChoices,
                lang: currentLang,
                current_address: currentGPS.address || schoolInfo.location || '',
                device_id: deviceId,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            appendChatMessage('model', extractApiError(data, trans?.errorConnection || 'Request failed'));
            return;
        }
        if (data.status === 'success') {
            if (data.personalized) {
                taskPersonalizedCache[selectedTaskId] = data.personalized;
                showPersonalizedPanel(data.personalized);
                const ttsText = (data.personalized.content || '').replace(/(\*|_)/g, '');
                if (ttsText) speakText(ttsText.slice(0, 500));
            }
        } else {
            appendChatMessage('model', extractApiError(data, trans?.errorConnection || 'Request failed'));
        }
    } catch (e) {
        console.error('Personalize failed', e);
    } finally {
        hideLoading();
        if (btn) { btn.disabled = false; btn.innerText = trans.personalizeTaskBtn || 'AI personalized steps'; }
    }
}

async function completeSelectedTask() {
    if (!selectedTaskId) {
        const next = roadmapData?.next_tasks?.[0];
        if (next) selectedTaskId = next.id;
        else return;
    }
    await completeTask(selectedTaskId);
}

async function completeTask(taskId) {
    try {
        const res = await fetch('/api/tasks/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId, task_id: taskId, lang: currentLang, branch_choices: branchChoices })
        });
        const data = await res.json();
        if (data.status === 'success') {
            completedTasks = data.completed_tasks;
            localStorage.setItem('completedTasks', JSON.stringify(completedTasks));
            roadmapData = data.roadmap;
            selectedTaskId = data.roadmap?.next_tasks?.[0]?.id || taskId;
            lastAgentFingerprint = null;
            renderRoadmap();
            await fetchAgentDecision(null, 'completed');
        }
    } catch (e) {
        console.error('Failed to complete task', e);
    }
}

function getAgentFingerprint() {
    return JSON.stringify({
        completed: completedTasks,
        lang: currentLang,
        next: roadmapData?.next_tasks?.[0]?.id || null,
    });
}

async function viewRoadmapPdf() {
    const trans = uiTranslations[currentLang] || {};
    if (!schoolInfo) {
        alert(trans.exportPdfMissingData || trans.errorFillAllFields || 'Please complete onboarding first.');
        return;
    }
    if (!roadmapData) {
        await fetchRoadmap();
    }
    if (!roadmapData) {
        alert(trans.exportPdfError || 'PDF export failed');
        return;
    }

    const exportBtns = document.querySelectorAll('#exportPdfBtn, .pdf-export-trigger');
    const prevLabels = new Map();
    exportBtns.forEach(btn => {
        prevLabels.set(btn, btn.innerText);
        btn.disabled = true;
        if (btn.id === 'exportPdfBtn') {
            btn.innerText = trans.exportPdfLoading || 'Generating...';
        }
    });

    const loadingTextEl = document.querySelector('#globalLoadingOverlay .loading-text');
    const prevLoadingText = loadingTextEl?.innerText;
    if (loadingTextEl && trans.exportPdfLoading) {
        loadingTextEl.innerText = trans.exportPdfLoading;
    }
    showLoading();

    try {
        const buf = await fetchRoadmapPdfBuffer();
        if (currentPdfBlobUrl) URL.revokeObjectURL(currentPdfBlobUrl);
        const blob = new Blob([buf], { type: 'application/pdf' });
        currentPdfBlobUrl = URL.createObjectURL(blob);
        const frame = document.getElementById('pdfViewerFrame');
        const panel = document.getElementById('pdfViewerPanel');
        if (frame) frame.src = currentPdfBlobUrl;
        panel?.classList.remove('hidden');
        panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        switchView('stage');
    } catch (e) {
        alert(e.message || trans.exportPdfError || 'PDF export failed');
    } finally {
        hideLoading();
        exportBtns.forEach(btn => {
            btn.disabled = false;
            if (btn.id === 'exportPdfBtn') {
                btn.innerText = prevLabels.get(btn) || trans.exportPdfBtn || 'Export PDF';
            }
        });
        if (loadingTextEl && prevLoadingText) loadingTextEl.innerText = prevLoadingText;
    }
}

async function fetchRoadmapPdfBuffer() {
    const trans = uiTranslations[currentLang] || {};
    const res = await fetch('/api/export/roadmap-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            device_id: deviceId,
            school_info: schoolInfo,
            completed_tasks: completedTasks,
            lang: currentLang,
            current_address: currentGPS.address || schoolInfo.location || '',
        }),
    });
    if (!res.ok) {
        let detail = trans.exportPdfError || 'PDF export failed';
        try {
            const errJson = await res.json();
            if (errJson.detail) detail = errJson.detail;
        } catch (_) { /* not JSON */ }
        throw new Error(detail);
    }
    const buf = await res.arrayBuffer();
    const header = new Uint8Array(buf.slice(0, 4));
    const isPdf = header[0] === 0x25 && header[1] === 0x50 && header[2] === 0x44 && header[3] === 0x46;
    if (!isPdf || buf.byteLength < 200) {
        throw new Error(trans.exportPdfError || 'PDF export failed');
    }
    return buf;
}

function closePdfViewer() {
    const panel = document.getElementById('pdfViewerPanel');
    const frame = document.getElementById('pdfViewerFrame');
    panel?.classList.add('hidden');
    if (frame) frame.src = '';
}

async function downloadCurrentPdf() {
    const trans = uiTranslations[currentLang] || {};
    try {
        const buf = currentPdfBlobUrl
            ? await (await fetch(currentPdfBlobUrl)).arrayBuffer()
            : await fetchRoadmapPdfBuffer();
        const blob = new Blob([buf], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `haru-action-plan-${currentLang}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
        alert(e.message || trans.exportPdfError || 'PDF export failed');
    }
}

async function downloadRoadmapPdf() {
    await viewRoadmapPdf();
}

async function submitOnboard() {
    const school_name = (typeof getSchoolFieldValue === 'function' ? getSchoolFieldValue() : document.getElementById('schoolName').value).trim();
    const arrival_date = document.getElementById('arrivalDate').value;
    const location = (typeof getLocationFieldValue === 'function' ? getLocationFieldValue() : document.getElementById('location').value).trim();
    const japanese_level = document.getElementById('japaneseLevel').value;
    const has_residence_card = document.getElementById('hasResidenceCard')?.checked || false;
    const housing_type = document.getElementById('housingType').value;
    const school_type = document.getElementById('schoolType').value;
    const part_time_plan = document.getElementById('partTimePlan').value;
    const sim_at_airport = document.getElementById('simAtAirport').checked;
    const already_exchanged = document.getElementById('alreadyExchanged').checked;
    const permit_obtained = document.getElementById('permitObtained')?.checked || false;

    if(!school_name || !arrival_date || !location) {
        const trans = uiTranslations[currentLang];
        alert(trans.errorFillAllFields);
        return;
    }

    completedTasks = [];
    // has_residence_card checkbox implies task_immigration is done
    if (has_residence_card) {
        completedTasks.push('task_immigration');
    }
    document.querySelectorAll('.onboard-task-chk:checked').forEach(chk => {
        const tid = chk.getAttribute('data-task-id');
        if (tid && !completedTasks.includes(tid)) completedTasks.push(tid);
    });

    schoolInfo = {
        school_name, arrival_date, location, japanese_level, has_residence_card,
        housing_type, school_type, part_time_plan, sim_at_airport, already_exchanged,
        permit_obtained
    };

    localStorage.setItem('schoolInfo', JSON.stringify(schoolInfo));
    localStorage.setItem('completedTasks', JSON.stringify(completedTasks));

    // Show loading overlay immediately — /api/user/init may call Gemini AI (10-30s)
    const trans = uiTranslations[currentLang] || {};
    const onboardBtn = document.getElementById('onboardBtn');
    if (onboardBtn) {
        onboardBtn.disabled = true;
        onboardBtn.innerText = trans.onboardingLoading || (trans.agentThinkingOverlay || 'Processing…');
    }
    showLoading();

    try {
        const res = await fetch('/api/user/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                school_info: { ...schoolInfo, lang: currentLang },
                completed_tasks: completedTasks
            })
        });
        const data = await res.json();
        if (data.roadmap) {
            roadmapData = data.roadmap;
            mergeRoadmapCompletedFromResponse(data.roadmap);
        }
    } catch (e) {
        console.error("Failed to sync init to backend", e);
    } finally {
        hideLoading();
        if (onboardBtn) {
            onboardBtn.disabled = false;
            onboardBtn.innerText = trans.onboardBtn || 'Activate';
        }
    }

    showWorkspace();
    cancelOnboardEdit();
    renderRoadmap();
    // Apply AI personalization immediately if returned with the init response
    if (roadmapData?.ai_personalization) {
        updateStatusHero(roadmapData);
        applyMissionFromRoadmap();
    }
    startLocationTracking();
}

function startLocationTracking() {
    startGPSAndFetchStep();
    if (locationTimerId) clearInterval(locationTimerId);
    locationTimerId = setInterval(() => {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => syncLocationFromCoords(position.coords.latitude, position.coords.longitude, false),
                (error) => console.error('Periodic location tracking failed', error),
                { maximumAge: 60000, timeout: 15000 }
            );
        }
    }, 5 * 60 * 1000);
}

async function syncLocationFromCoords(latitude, longitude, refreshAgent = false) {
    currentGPS.latitude = latitude;
    currentGPS.longitude = longitude;
    const trans = uiTranslations[currentLang] || {};
    try {
        const res = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json&accept-language=${currentLang}`
        );
        const data = await res.json();
        currentGPS.address = data.display_name || trans.unknownLocation || 'Unknown Japan Location';
    } catch (e) {
        currentGPS.address = `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
    }

    const shortAddr = (currentGPS.address || '').split(',')[0].trim();
    if (shortAddr) setGpsStatusText(shortAddr.slice(0, 28));

    fetch('/api/user/location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            device_id: deviceId,
            latitude: currentGPS.latitude,
            longitude: currentGPS.longitude,
            address: currentGPS.address,
        }),
    }).catch((e) => console.error(e));

    if (refreshAgent) {
        if (!currentDecisionObj) {
            await fetchAgentDecision(null, null, true);
        } else {
            renderAgentDecision();
        }
    }
}

function startGPSAndFetchStep() {
    const trans = uiTranslations[currentLang];

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                setGpsStatusText(trans.locationTracking);
                await syncLocationFromCoords(position.coords.latitude, position.coords.longitude, true);
            },
            (error) => {
                setGpsStatusText(trans.locationFailed);
                currentGPS.address = schoolInfo.location;
                if (!currentDecisionObj) {
                    fetchAgentDecision(null, null, true);
                } else {
                    renderAgentDecision();
                }
            }
        );
    } else {
        setGpsStatusText(trans.locationFailed);
        currentGPS.address = schoolInfo.location;
        if (!currentDecisionObj) {
            fetchAgentDecision(null, null, true);
        } else {
            renderAgentDecision();
        }
    }
}

function renderAgentDecision() {
    if (isStaleMockDecision(currentDecisionObj)) {
        applyMissionFromRoadmap();
        return;
    }
    if (!currentDecisionObj) {
        applyMissionFromRoadmap();
        return;
    }
    const d = currentDecisionObj;
    
    const getLocString = (val) => typeof val === 'object' ? (val[currentLang] || val['en'] || val['zh-TW'] || Object.values(val)[0]) : val;
    
    const face = agentFaces[d.expression] || "H";
    const agentFaceEl = document.getElementById('agentFace');
    if (agentFaceEl) agentFaceEl.innerText = face;
    document.getElementById('currentFocusTitle').innerText = getLocString(d.current_focus_title);
    document.getElementById('agentSpeech').innerHTML = marked.parse(getLocString(d.narrative));
    document.getElementById('upcomingHint').innerText = getLocString(d.upcoming_hint);

    currentAgentAction = { type: d.action_type, data: d.action_data };
    const actionArea = document.getElementById('actionArea');
    const actionBtn = document.getElementById('agentActionButton');
    const inlineMapPanel = document.getElementById('inlineMapPanel');
    const inlineMapFrame = document.getElementById('inlineMapFrame');
    const mapFrame = document.getElementById('dynamicMapFrame');
    
    if (d.action_type !== "none") {
        actionArea.classList.remove('hidden');
        actionBtn.innerText = getLocString(d.action_label);
        
        if (d.action_type === "navigation" && d.action_data) {
            const query = encodeURIComponent(d.action_data);
            const src = `https://maps.google.com/maps?q=${query}&t=&z=15&ie=UTF8&iwloc=&output=embed`;
            if (inlineMapFrame) inlineMapFrame.src = src;
            if (mapFrame) mapFrame.src = src;
            inlineMapPanel?.classList.remove('hidden');
        } else {
            if (inlineMapFrame) inlineMapFrame.src = '';
            if (mapFrame) mapFrame.src = '';
            inlineMapPanel?.classList.add('hidden');
        }
        
        if (d.action_type === "document_scan") {
            openScannerSheet();
        }
    } else {
        actionArea.classList.add('hidden');
        if (inlineMapFrame) inlineMapFrame.src = '';
        if (mapFrame) mapFrame.src = '';
        inlineMapPanel?.classList.add('hidden');
    }
    
    // Play speech only when narrative actually changed
    const textToSpeak = getLocString(d.narrative).replace(/(\*|_)/g, '');
    if (textToSpeak && textToSpeak !== lastSpokenNarrative) {
        lastSpokenNarrative = textToSpeak;
        speakText(textToSpeak);
    }
}

async function fetchAgentDecision(problemReport = null, taskAction = null, forceRefresh = false) {
    const fp = getAgentFingerprint();
    if (
        !problemReport && !taskAction && !forceRefresh
        && fp === lastAgentFingerprint
        && currentDecisionObj
    ) {
        renderAgentDecision();
        return;
    }
    showLoading();
    document.getElementById('agentFace').innerText = agentFaces["thinking"];
    
    const now = new Date();
    const localTimeISO = now.getFullYear() + '-' + 
        String(now.getMonth() + 1).padStart(2, '0') + '-' + 
        String(now.getDate()).padStart(2, '0') + 'T' + 
        String(now.getHours()).padStart(2, '0') + ':' + 
        String(now.getMinutes()).padStart(2, '0');
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const dayOfWeek = days[now.getDay()];

    currentAbortController = new AbortController();

    try {
        const res = await fetch('/api/agent-step', {
            method: 'POST',
            signal: currentAbortController.signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                current_address: currentGPS.address,
                latitude: currentGPS.latitude,
                longitude: currentGPS.longitude,
                local_time: localTimeISO,
                day_of_week: dayOfWeek,
                lang: currentLang,
                device_id: deviceId,
                problem_report: problemReport,
                task_action: taskAction,
                force_llm: true
            })
        });
        const data = await res.json();
        if(data.status === 'success') {
            if (isStaleMockDecision(data.decision) && !problemReport && !taskAction) {
                // Store the mock decision so the fingerprint cache works,
                // preventing fetchRoadmap from triggering another agent-step call.
                currentDecisionObj = data.decision;
                lastAgentFingerprint = getAgentFingerprint();
                localStorage.setItem('currentDecisionObj', JSON.stringify(currentDecisionObj));
                applyMissionFromRoadmap();
            } else {
                currentDecisionObj = data.decision;
                lastAgentFingerprint = getAgentFingerprint();
                localStorage.setItem('currentDecisionObj', JSON.stringify(currentDecisionObj));
                renderAgentDecision();
            }
            if (data.completed_tasks) {
                // Only re-fetch roadmap when the server actually added newly completed tasks
                const prevLen = completedTasks.length;
                completedTasks = data.completed_tasks;
                localStorage.setItem('completedTasks', JSON.stringify(completedTasks));
                if (completedTasks.length !== prevLen) {
                    fetchRoadmap();
                }
            }
        } else {
            throw new Error(data.detail || "Agent decision failed");
        }
    } catch (err) {
        if (err.name === 'AbortError') return;
        console.error(err);
        const trans = uiTranslations[currentLang];
        document.getElementById('agentFace').innerText = agentFaces["alert"];
        document.getElementById('currentFocusTitle').innerText = trans ? trans.errorConnectionTitle : "Connection Error";
        document.getElementById('agentSpeech').innerHTML = `<p style="color:var(--sub)">${trans ? trans.errorConnectionMsg : err.message}</p>`;
        document.getElementById('actionArea').classList.add('hidden');
    } finally {
        hideLoading();
    }
}

function markTaskCompleted() {
    completeSelectedTask();
}

function reportProblem() {
    document.getElementById('problemReportArea').classList.remove('hidden');
}

function submitProblem() {
    const text = document.getElementById('problemReportText').value.trim();
    if (!text) return;
    
    // Add to chat history visually
    appendChatMessage('user', text);
    chatHistory.push({ role: 'user', text: text });
    
    document.getElementById('problemReportArea').classList.add('hidden');
    document.getElementById('problemReportText').value = '';
    
    // Fetch new decision with problem report
    fetchAgentDecision(text);
}

function triggerAgentAction() {
    if (!currentAgentAction) return;
    
    if (currentAgentAction.type === "navigation") {
        openMapWithQuery(currentAgentAction.data);
    }
    else if (currentAgentAction.type === "document_scan") {
        openScannerSheet();
    }
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

function renderLinkChipHtml(link) {
    const trans = uiTranslations[currentLang] || {};
    const tierClass = link.tier === 'official' ? 'link-chip-official' : 'link-chip-semi';
    const badge = link.tier === 'official'
        ? (trans.officialBadge || 'Official')
        : (trans.semiOfficialBadge || 'Semi-official');
    return `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer" class="link-chip ${tierClass}" title="${escapeHtml(link.summary || '')}">
        <span class="link-chip-badge">${badge}</span>
        <span class="link-chip-label">${escapeHtml(link.label)}</span>
    </a>`;
}

function renderOfficialLinks(links, containerEl) {
    if (!containerEl) return;
    if (!links || !links.length) {
        containerEl.innerHTML = '';
        return;
    }
    const trans = uiTranslations[currentLang] || {};
    containerEl.innerHTML = `
        <div class="detail-label">${trans.officialLinksTitle || 'Official links'}</div>
        <div class="official-links-wrap">${links.map(renderLinkChipHtml).join('')}</div>`;
}

function blocksToPlainText(blocks) {
    return (blocks || [])
        .filter(b => b.type === 'text')
        .map(b => b.content || '')
        .join('\n')
        .trim();
}

let mermaidReady = false;
let mermaidRenderSeq = 0;

async function ensureMermaid() {
    if (!window.mermaid) return null;
    if (!mermaidReady) {
        window.mermaid.initialize({
            startOnLoad: false,
            securityLevel: 'loose',
            theme: 'neutral',
            flowchart: { useMaxWidth: true, htmlLabels: false },
        });
        mermaidReady = true;
    }
    return window.mermaid;
}

async function renderMermaidInto(el, source) {
    const mermaid = await ensureMermaid();
    if (!mermaid || !el) return;
    const src = (source || '').trim();
    if (!src) return;
    el.classList.add('mermaid-loading');
    const renderId = `haru-mermaid-${Date.now()}-${++mermaidRenderSeq}`;
    try {
        const { svg } = await mermaid.render(renderId, src);
        el.innerHTML = svg;
        el.classList.remove('mermaid-error-state', 'mermaid-loading');
    } catch (err) {
        const trans = uiTranslations[currentLang] || {};
        el.classList.add('mermaid-error-state');
        el.classList.remove('mermaid-loading');
        el.innerHTML = `<pre class="mermaid-error">${escapeHtml(err.message || trans.mermaidRenderError || 'Diagram could not be rendered')}</pre>`;
    }
}

function splitTextWithMermaid(content) {
    const text = content || '';
    const re = /```mermaid\s*\n([\s\S]*?)```/gi;
    const parts = [];
    let last = 0;
    let match;
    while ((match = re.exec(text)) !== null) {
        if (match.index > last) {
            parts.push({ type: 'text', content: text.slice(last, match.index) });
        }
        parts.push({ type: 'mermaid', source: (match[1] || '').trim() });
        last = match.index + match[0].length;
    }
    if (last < text.length) {
        parts.push({ type: 'text', content: text.slice(last) });
    }
    return parts.length ? parts : [{ type: 'text', content: text }];
}

function buildMermaidBlockElement(block) {
    const trans = uiTranslations[currentLang] || {};
    const wrap = document.createElement('div');
    wrap.className = 'chat-mermaid-block';
    const title = block.title || '';
    if (title) {
        const titleEl = document.createElement('div');
        titleEl.className = 'chat-block-title';
        titleEl.textContent = title;
        wrap.appendChild(titleEl);
    }
    const diagram = document.createElement('div');
    diagram.className = 'mermaid-diagram';
    wrap.appendChild(diagram);
    renderMermaidInto(diagram, block.source || '');
    if (block.diagram_kind === 'roadmap') {
        const actions = document.createElement('div');
        actions.className = 'chat-mermaid-actions';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-secondary btn-pill-sm';
        btn.textContent = trans.openRoadmapBtn || 'Open full roadmap';
        btn.onclick = () => switchView('stage');
        actions.appendChild(btn);
        wrap.appendChild(actions);
    }
    return wrap;
}

function renderMessageBlock(block) {
    const trans = uiTranslations[currentLang] || {};
    if (block.type === 'text') {
        const parts = splitTextWithMermaid(block.content || '');
        if (parts.length === 1 && parts[0].type === 'text') {
            const div = document.createElement('div');
            div.className = 'markdown-content';
            div.innerHTML = marked.parse(parts[0].content || '');
            return div;
        }
        const wrap = document.createElement('div');
        wrap.className = 'chat-text-blocks';
        parts.forEach((part) => {
            if (part.type === 'text' && (part.content || '').trim()) {
                const div = document.createElement('div');
                div.className = 'markdown-content';
                div.innerHTML = marked.parse(part.content || '');
                wrap.appendChild(div);
            } else if (part.type === 'mermaid') {
                wrap.appendChild(buildMermaidBlockElement({ source: part.source, diagram_kind: 'custom' }));
            }
        });
        return wrap;
    }
    if (block.type === 'kb_snippet') {
        const wrap = document.createElement('div');
        wrap.className = 'kb-snippet-block';
        wrap.innerHTML = `<div class="kb-title">${escapeHtml(block.title || '')}</div>
            <div class="kb-body">${escapeHtml(block.content || '')}</div>`;
        return wrap;
    }
    if (block.type === 'guide_card') {
        const wrap = document.createElement('div');
        wrap.className = 'guide-card-block';
        const steps = block.step_count ? `<span style="font-size:0.55rem;color:var(--base-light)">${block.step_count} ${trans.guideStepsWord || 'steps'}</span>` : '';
        wrap.innerHTML = `
            <div class="guide-card-title">${escapeHtml(block.title || '')}</div>
            <p class="guide-card-desc">${escapeHtml(block.description || '')}</p>
            ${steps}
            <button type="button" class="btn-accent-sm guide-launch-btn" style="width:100%;margin-top:0.35rem">
                ${escapeHtml(block.cta_label || trans.startWalkthrough || 'Start walkthrough')}
            </button>`;
        wrap.querySelector('button').onclick = () => openGuideWalkthrough(block.guide_id);
        return wrap;
    }
    if (block.type === 'source_citations') {
        const wrap = document.createElement('div');
        const title = block.title || trans.citedSourcesLabel || 'Sources';
        wrap.innerHTML = `<div class="chat-block-title">${escapeHtml(title)}</div>
            <div class="chat-link-chips">${(block.items || []).map(renderLinkChipHtml).join('')}</div>`;
        return wrap;
    }
    if (block.type === 'link_chips') {
        const wrap = document.createElement('div');
        const title = block.title
            ? (typeof block.title === 'string' ? block.title : (block.title[currentLang] || block.title['en'] || block.title['zh-TW']))
            : (trans.linkChipsTitle || 'Official links');
        wrap.innerHTML = `<div class="chat-block-title">${escapeHtml(title)}</div>
            <div class="chat-link-chips">${(block.items || []).map(renderLinkChipHtml).join('')}</div>`;
        return wrap;
    }
    if (block.type === 'chips') {
        const wrap = document.createElement('div');
        wrap.className = 'chips-row';
        (block.items || []).forEach(chip => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-action-chip';
            btn.innerText = chip.label;
            btn.onclick = () => onChatChipAction(chip);
            wrap.appendChild(btn);
        });
        return wrap;
    }
    if (block.type === 'map_embed') {
        const wrap = document.createElement('div');
        wrap.className = 'chat-map-block';
        const title = block.title || trans.mapBlockTitle || 'Map';
        const label = block.label || block.query || '';
        const openLabel = trans.openInGoogleMaps || 'Open in Google Maps';
        wrap.innerHTML = `
            <div class="chat-block-title">${escapeHtml(title)}</div>
            <div class="chat-map-label">${escapeHtml(label)}</div>
            <div class="chat-map-frame-wrap">
                <iframe src="${escapeHtml(block.embed_url || '')}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" title="${escapeHtml(label)}"></iframe>
            </div>
            <a href="${escapeHtml(block.open_url || block.embed_url || '#')}" target="_blank" rel="noopener noreferrer" class="chat-map-open-link">${escapeHtml(openLabel)}</a>`;
        return wrap;
    }
    if (block.type === 'mermaid') {
        return buildMermaidBlockElement(block);
    }
    if (block.type === 'ai_question') {
        const wrap = document.createElement('div');
        wrap.className = 'ai-question-block';
        wrap.innerHTML = `<div class="ai-question-prompt">${escapeHtml(block.question || '')}</div><div class="ai-question-choices"></div>`;
        const choicesEl = wrap.querySelector('.ai-question-choices');
        (block.choices || []).forEach((choice, idx) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ai-question-choice-btn';
            const letter = String.fromCharCode(65 + idx);
            btn.innerHTML = `<span class="ai-question-letter">${letter}.</span>${escapeHtml(choice.label || '')}`;
            btn.onclick = () => submitAiQuestionAnswer(choice, block.question);
            choicesEl.appendChild(btn);
        });
        return wrap;
    }
    if (block.type === 'quiz_question') {
        const wrap = document.createElement('div');
        wrap.className = 'quiz-question-block';
        const progress = block.total
            ? `<div class="quiz-progress"><span class="quiz-progress-badge">${(trans.quizProgress || 'Question {n}/{total}').replace('{n}', block.question_index).replace('{total}', block.total)}</span></div>`
            : '';
        wrap.innerHTML = `${progress}<div class="quiz-prompt">${escapeHtml(block.prompt || '')}</div>
            <div class="quiz-choices"></div>`;
        const choicesEl = wrap.querySelector('.quiz-choices');
        (block.choices || []).forEach((choice, idx) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'quiz-choice-btn';
            const letter = ['A', 'B', 'C', 'D'][idx] || String(idx + 1);
            btn.innerHTML = `
                <span class="quiz-choice-badge">${letter}</span>
                <span class="quiz-choice-text">${escapeHtml(choice.label || '')}</span>
                <span class="material-symbols-outlined quiz-choice-arrow">chevron_right</span>`;
            btn.onclick = () => submitQuizAnswer(choice.id, choice.label, wrap);
            choicesEl.appendChild(btn);
        });
        return wrap;
    }
    if (block.type === 'images') {
        const wrap = document.createElement('div');
        wrap.className = 'chat-image-grid';
        (block.items || []).forEach(item => {
            const src = item.url || item.preview || '';
            if (!src) return;
            const img = document.createElement('img');
            img.src = src;
            img.alt = trans.chatImageAlt || 'attached';
            img.className = 'chat-attached-thumb';
            wrap.appendChild(img);
        });
        return wrap.children.length ? wrap : null;
    }
    return null;
}

function onChatChipAction(chip) {
    if (!chip) return;
    if (chip.action === 'send_message') {
        document.getElementById('chatInput').value = chip.payload || chip.label || '';
        sendMessage();
    } else if (chip.action === 'start_quiz') {
        startQuiz();
    } else if (chip.action === 'complete_task') {
        completeTask(chip.payload);
    } else if (chip.action === 'open_guide') {
        openGuideWalkthrough(chip.payload);
    } else if (chip.action === 'open_task') {
        selectRoadmapTask(chip.payload);
        switchView('stage');
    } else if (chip.action === 'open_maps') {
        openMapWithQuery(chip.payload || schoolInfo?.location || currentGPS.address || '');
    }
}

function updateComposerChips(chips) {
    const el = document.getElementById('chatComposerChips');
    if (!el) return;
    if (!chips || !chips.length) {
        el.classList.add('hidden');
        el.innerHTML = '';
        return;
    }
    el.classList.remove('hidden');
    el.innerHTML = '';
    chips.forEach(chip => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'composer-chip';
        btn.innerText = chip.label;
        btn.onclick = () => onChatChipAction(chip);
        el.appendChild(btn);
    });
}

async function refreshComposerChips(taskId) {
    if (!taskId) {
        updateComposerChips([]);
        return;
    }
    try {
        const res = await fetch(`/api/chat/suggestions?task_id=${encodeURIComponent(taskId)}&lang=${encodeURIComponent(currentLang)}`);
        const data = await res.json();
        if (data.status === 'success') {
            updateComposerChips(data.chips || []);
        }
    } catch (e) {
        console.warn('Failed to load composer chips', e);
    }
}

function renderChatHistory() {
    const chatWindow = document.getElementById('chatWindow');
    chatWindow.innerHTML = "";
    chatHistory.forEach(msg => {
        if (msg.blocks && msg.blocks.length) {
            appendStructuredMessage(msg.role, msg.blocks, msg.role === 'model');
        } else if (msg.text) {
            appendChatMessage(msg.role, msg.text, msg.role === 'model');
        }
    });
}

function appendStructuredMessage(role, blocks, isMarkdown = true) {
    const chatWindow = document.getElementById('chatWindow');
    const trans = uiTranslations[currentLang] || {};
    const wrapper = document.createElement('div');
    wrapper.className = `chat-row ${role === 'user' ? 'user' : 'model'}`;

    const meta = document.createElement('div');
    meta.className = 'chat-meta';
    if (role === 'user') {
        meta.innerText = trans.chatUserLabel || 'You';
    } else {
        meta.innerHTML = `<span class="chat-meta-avatar"><span class="material-symbols-outlined">auto_awesome</span></span><span>${escapeHtml(trans.haruAiLabel || 'HARU AI')}</span>`;
    }
    wrapper.appendChild(meta);

    const messageBox = document.createElement('div');
    messageBox.className = role === 'user' ? 'bubble bubble-user' : 'bubble bubble-ai';

    if (role === 'user') {
        const inner = document.createElement('div');
        inner.className = 'chat-blocks-wrap user-blocks';
        let hasContent = false;
        (blocks || []).forEach(block => {
            const node = renderMessageBlock(block);
            if (node) {
                inner.appendChild(node);
                hasContent = true;
            } else if (block.type === 'text' && block.content) {
                const t = document.createElement('div');
                t.innerText = block.content;
                inner.appendChild(t);
                hasContent = true;
            }
        });
        if (!hasContent) {
            messageBox.innerText = blocksToPlainText(blocks) || '';
        } else {
            messageBox.appendChild(inner);
        }
    } else {
        const inner = document.createElement('div');
        inner.className = 'chat-blocks-wrap';
        (blocks || []).forEach(block => {
            const node = renderMessageBlock(block);
            if (node) inner.appendChild(node);
        });
        messageBox.appendChild(inner);
    }

    wrapper.appendChild(messageBox);
    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendChatMetaFootnote(data) {
    if (!data || data.status !== 'success') return;
    const trans = uiTranslations[currentLang] || {};
    let note = '';
    if (data.mock_mode) {
        note = trans.chatMockModeNote || 'Demo mode: set an API key in Profile for live search.';
    } else if (data.used_search === false) {
        note = trans.chatNoSearchNote || 'Live search was unavailable for this reply.';
    } else if (data.used_search === true) {
        note = trans.chatSearchUsedNote || 'Answer includes Google Search results.';
    }
    if (!note) return;
    const chatWindow = document.getElementById('chatWindow');
    const foot = document.createElement('div');
    foot.className = 'chat-meta-footnote';
    foot.innerText = note;
    chatWindow.appendChild(foot);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendChatMessage(role, text, isMarkdown = true) {
    if (role === 'model' && Array.isArray(text)) {
        appendStructuredMessage(role, text, isMarkdown);
        return;
    }
    const blocks = [{ type: 'text', content: text }];
    if (role === 'user') {
        appendStructuredMessage(role, blocks, false);
        return;
    }
    appendStructuredMessage(role, blocks, isMarkdown);
}

function sanitizeHistoryForStorage(history) {
    return (history || []).map(msg => {
        if (!msg.blocks) return msg;
        return {
            ...msg,
            blocks: msg.blocks.map(b => {
                if (b.type === 'images') {
                    return {
                        type: 'images',
                        items: (b.items || []).map(i => ({
                            preview: (i.preview || i.url || '').slice(0, 200),
                            mime_type: i.mime_type || 'image/jpeg',
                        })),
                    };
                }
                return b;
            }),
        };
    });
}

function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function renderChatImagePreviews() {
    const el = document.getElementById('chatImagePreview');
    if (!el) return;
    const trans = uiTranslations[currentLang] || {};
    if (!chatPendingImages.length) {
        el.classList.add('hidden');
        el.innerHTML = '';
        return;
    }
    el.classList.remove('hidden');
    el.innerHTML = '';
    chatPendingImages.forEach((img, idx) => {
        const wrap = document.createElement('div');
        wrap.className = 'chat-preview-item';
        wrap.innerHTML = `<img src="${img.dataUrl}" alt="" class="chat-preview-thumb">
            <button type="button" class="chat-preview-remove" title="${trans.removeImage || 'Remove'}">×</button>`;
        wrap.querySelector('button').onclick = () => removeChatPendingImage(idx);
        el.appendChild(wrap);
    });
}

function removeChatPendingImage(index) {
    chatPendingImages.splice(index, 1);
    renderChatImagePreviews();
}

function clearChatPendingImages() {
    chatPendingImages = [];
    renderChatImagePreviews();
    const input = document.getElementById('chatImageInput');
    if (input) input.value = '';
}

async function handleChatImageSelect(event) {
    const trans = uiTranslations[currentLang] || {};
    const files = Array.from(event.target.files || []);
    for (const file of files) {
        if (chatPendingImages.length >= MAX_CHAT_IMAGES) {
            alert((trans.chatImageMax || 'You can attach up to {n} photos').replace('{n}', MAX_CHAT_IMAGES));
            break;
        }
        if (!file.type.startsWith('image/')) continue;
        if (file.size > 4 * 1024 * 1024) {
            alert(trans.chatImageTooLarge || 'Each image must be under 4MB');
            continue;
        }
        const dataUrl = await readFileAsDataUrl(file);
        chatPendingImages.push({
            dataUrl,
            dataBase64: dataUrl,
            mime_type: file.type || 'image/jpeg',
        });
    }
    renderChatImagePreviews();
    event.target.value = '';
}

async function startQuiz() {
    if (quizState && quizState.active) return;
    const trans = uiTranslations[currentLang] || {};
    showLoading();
    try {
        const focusTaskId = selectedTaskId || (roadmapData?.next_tasks?.[0]?.id) || null;
        const res = await fetch('/api/quiz/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                lang: currentLang,
                focus_task_id: focusTaskId,
            }),
        });
        const data = await res.json();
        if (data.status === 'success' && data.message_blocks) {
            quizState = data.quiz_state || null;
            appendStructuredMessage('model', data.message_blocks);
            chatHistory.push({ role: 'model', blocks: data.message_blocks });
            localStorage.setItem('chatHistory', JSON.stringify(sanitizeHistoryForStorage(chatHistory)));
            const ttsText = blocksToPlainText(data.message_blocks);
            if (ttsText) speakText(ttsText.replace(/(\*|_)/g, ''));
        }
    } catch (err) {
        console.error(err);
        appendChatMessage('model', trans.errorConnection || 'Connection error.');
    } finally {
        hideLoading();
    }
}

async function submitQuizAnswer(choiceId, choiceLabel, questionEl) {
    if (!quizState || !quizState.active) return;
    const trans = uiTranslations[currentLang] || {};
    if (questionEl) {
        questionEl.querySelectorAll('.quiz-choice-btn').forEach(btn => {
            btn.disabled = true;
        });
    }
    appendChatMessage('user', choiceLabel);
    chatHistory.push({ role: 'user', text: choiceLabel });
    showLoading();
    try {
        const res = await fetch('/api/quiz/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                quiz_state: quizState,
                choice_id: choiceId,
                school_info: schoolInfo,
                completed_tasks: completedTasks,
                lang: currentLang,
                device_id: deviceId,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            appendChatMessage('model', extractApiError(data, trans.errorConnection || 'Request failed'));
            return;
        }
        if (data.status === 'success') {
            quizState = data.quiz_state || null;
            if (data.message_blocks && data.message_blocks.length) {
                appendStructuredMessage('model', data.message_blocks);
                chatHistory.push({ role: 'model', blocks: data.message_blocks });
                const ttsText = blocksToPlainText(data.message_blocks);
                if (ttsText) speakText(ttsText.replace(/(\*|_)/g, ''));
            }
            if (data.suggested_task_ids && data.suggested_task_ids.length) {
                selectRoadmapTask(data.suggested_task_ids[0]);
            }
            localStorage.setItem('chatHistory', JSON.stringify(sanitizeHistoryForStorage(chatHistory)));
        }
    } catch (err) {
        console.error(err);
        appendChatMessage('model', trans.errorConnection || 'Connection error.');
    } finally {
        hideLoading();
    }
}

async function submitAiQuestionAnswer(choice, question) {
    const label = (choice && choice.label) ? choice.label.trim() : '';
    if (!label) return;
    const chatInput = document.getElementById('chatInput');
    if (!chatInput) return;
    chatInput.value = label;
    await sendMessage();
}

async function sendMessage() {
    const chatInput = document.getElementById('chatInput');
    const message = chatInput.value.trim();
    const hasImages = chatPendingImages.length > 0;
    if (!message && !hasImages) return;

    showLoading();
    const trans = uiTranslations[currentLang];

    const userBlocks = [];
    if (message) userBlocks.push({ type: 'text', content: message });
    if (hasImages) {
        userBlocks.push({
            type: 'images',
            items: chatPendingImages.map(img => ({
                url: img.dataUrl,
                preview: img.dataUrl,
                mime_type: img.mime_type,
            })),
        });
    }
    const imagesPayload = chatPendingImages.map(img => ({
        data_base64: img.dataBase64,
        mime_type: img.mime_type,
    }));

    appendStructuredMessage('user', userBlocks);
    chatInput.value = '';
    clearChatPendingImages();

    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    sendBtn.innerText = trans ? trans.sendBtnLoading : "Thinking...";

    chatHistory.push({ role: 'user', blocks: userBlocks });

    currentAbortController = new AbortController();

    try {
        const focusTaskId = selectedTaskId || (roadmapData?.next_tasks?.[0]?.id) || null;
        const res = await fetch('/api/chat', {
            method: 'POST',
            signal: currentAbortController.signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                school_info: schoolInfo,
                chat_history: chatHistory.slice(-8),
                lang: currentLang,
                completed_tasks: completedTasks,
                branch_choices: branchChoices,
                focus_task_id: focusTaskId,
                images: imagesPayload.length ? imagesPayload : null,
                device_id: deviceId,
                current_address: currentGPS.address || schoolInfo?.location || '',
                latitude: currentGPS.latitude,
                longitude: currentGPS.longitude,
            })
        });
        const data = await res.json();
        if (!res.ok) {
            appendChatMessage('model', extractApiError(data, trans ? trans.errorConnection : 'Request failed'));
            return;
        }
        if (data.status === 'success') {
            if (data.message && data.message.blocks) {
                appendStructuredMessage('model', data.message.blocks);
                chatHistory.push({ role: 'model', blocks: data.message.blocks });
                const ttsText = blocksToPlainText(data.message.blocks) || data.reply || '';
                if (ttsText) speakText(ttsText.replace(/(\*|_)/g, ''));
            } else if (data.reply) {
                appendChatMessage('model', data.reply);
                chatHistory.push({ role: 'model', text: data.reply });
                speakText(data.reply.replace(/(\*|_)/g, ''));
            }
            updateComposerChips(data.suggested_chips || []);
            appendChatMetaFootnote(data);
            localStorage.setItem('chatHistory', JSON.stringify(sanitizeHistoryForStorage(chatHistory)));
        } else {
            appendChatMessage('model', extractApiError(data, trans ? trans.errorConnection : 'Request failed'));
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            chatHistory.pop();
            const chatWindow = document.getElementById('chatWindow');
            chatWindow.removeChild(chatWindow.lastChild);
            return;
        }
        console.error(err);
        appendChatMessage('model', trans ? trans.errorConnection : "Connection error.");
    } finally {
        hideLoading();
        sendBtn.disabled = false;
        sendBtn.innerText = trans ? trans.sendBtn : "Send";
    }
}

let isRecording = false;
async function toggleSTT() {
    const dot = document.getElementById('micRecordingDot');
    if (isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        dot.classList.add('hidden');
    } else {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = e => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };
            
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append('file', audioBlob);
                formData.append('lang', currentLang);
                
                document.getElementById('chatInput').placeholder = uiTranslations[currentLang]?.sttListening || 'Listening...';
                try {
                    const res = await fetch('/api/stt', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (data.status === 'success' && data.text) {
                        document.getElementById('chatInput').value = data.text;
                        sendMessage();
                    }
                } catch (err) {
                    console.error("STT Error", err);
                }
                document.getElementById('chatInput').placeholder = uiTranslations[currentLang]?.chatPlaceholder || "";
                stream.getTracks().forEach(track => track.stop());
            };
            
            mediaRecorder.start();
            isRecording = true;
            dot.classList.remove('hidden');
        } catch (err) {
            console.error("Microphone access denied or error", err);
            alert(uiTranslations[currentLang]?.micPermissionDenied || 'Please allow microphone access');
        }
    }
}

async function analyzeForm() {
    const fileInput = document.getElementById('formImageFile');
    const file = fileInput.files[0];
    const trans = uiTranslations[currentLang];

    if(!file) {
        alert(trans ? trans.scannerDefaultText : "Please select an image first!");
        return;
    }

    showLoading();

    const analyzeBtn = document.getElementById('analyzeBtn');
    const resultBox = document.getElementById('analysisResult');
    analyzeBtn.disabled = true;
    analyzeBtn.innerText = trans ? trans.scannerBtnLoading : "Loading...";
    resultBox.classList.remove('hidden');
    resultBox.innerHTML = trans ? trans.scannerAnalyzing : "Analyzing...";

    const formData = new FormData();
    formData.append('file', file);
    formData.append('school_name', schoolInfo.school_name);
    formData.append('location', schoolInfo.location);
    formData.append('lang', currentLang);
    formData.append('device_id', deviceId);

    currentAbortController = new AbortController();

    try {
        const res = await fetch('/api/analyze-form', {
            method: 'POST',
            signal: currentAbortController.signal,
            body: formData
        });
        const data = await res.json();
        if(data.status === 'success') {
            resultBox.innerHTML = marked.parse(data.analysis);
        } else {
            resultBox.innerHTML = trans ? trans.errorAnalyzeFailed : "Error";
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            resultBox.classList.add('hidden');
            return;
        }
        console.error(err);
        resultBox.innerHTML = trans ? trans.errorConnection : "Error";
    } finally {
        hideLoading();
        analyzeBtn.disabled = false;
        analyzeBtn.innerText = trans ? trans.scannerBtn : "Analyze";
    }
}

function resetData() {
    const trans = uiTranslations[currentLang];
    if(confirm(trans ? trans.resetConfirm : "Reset all data?")) {
        localStorage.clear();
        window.location.reload();
    }
}

function switchTab(tabName) {
    if (tabName === 'chat') switchView('talk');
    else switchView('stage');
}

window.switchTab = switchTab;

window.selectBranchChoice = selectBranchChoice;
