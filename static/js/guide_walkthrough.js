/** Interactive service guide walkthrough panel */
let activeGuide = null;
let activeGuideStep = 0;

async function openGuideWalkthrough(guideId) {
    const trans = (window.uiTranslations && window.uiTranslations[currentLang]) || {};
    try {
        const res = await fetch(`/api/guides/${encodeURIComponent(guideId)}?lang=${encodeURIComponent(currentLang)}`);
        const data = await res.json();
        if (data.status !== 'success' || !data.guide) throw new Error('guide not found');
        activeGuide = data.guide;
        activeGuideStep = 0;
        renderGuidePanel();
        document.getElementById('guideWalkthroughPanel')?.classList.remove('hidden');
        document.body.classList.add('guide-open');
    } catch (e) {
        console.error(e);
        alert(trans.guideLoadError || 'Could not load guide');
    }
}

function closeGuideWalkthrough() {
    document.getElementById('guideWalkthroughPanel')?.classList.add('hidden');
    document.body.classList.remove('guide-open');
    activeGuide = null;
    activeGuideStep = 0;
}

function guideNextStep() {
    if (!activeGuide) return;
    if (activeGuideStep < activeGuide.steps.length - 1) {
        activeGuideStep++;
        renderGuidePanel();
    }
}

function guidePrevStep() {
    if (!activeGuide || activeGuideStep <= 0) return;
    activeGuideStep--;
    renderGuidePanel();
}

function toggleGuideChecklist(stepIdx, itemIdx) {
    if (!activeGuide || !activeGuide.steps[stepIdx]) return;
    const item = activeGuide.steps[stepIdx].checklist[itemIdx];
    if (item) item.checked = !item.checked;
    renderGuidePanel();
}

function renderGuidePanel() {
    const panel = document.getElementById('guideWalkthroughBody');
    if (!panel || !activeGuide) return;
    const trans = (window.uiTranslations && window.uiTranslations[currentLang]) || {};
    const step = activeGuide.steps[activeGuideStep];
    const total = activeGuide.steps.length;
    const pct = Math.round(((activeGuideStep + 1) / total) * 100);

    let sourcesHtml = '';
    if (activeGuide.sources && activeGuide.sources.length) {
        sourcesHtml = `<div class="guide-sources">
            <div class="detail-label">${escapeHtml(trans.citedSourcesLabel || 'Sources')}</div>
            ${activeGuide.sources.map(s => `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener" class="link-chip link-chip-official" style="margin-bottom:0.25rem"><span class="link-chip-badge">${s.tier === 'official' ? (trans.officialBadge || 'Official') : 'Ref'}</span><span class="link-chip-label">${escapeHtml(s.label)}</span></a>`).join('')}
        </div>`;
    }

    const checklistHtml = (step.checklist || []).map((item, i) =>
        `<label class="check-list" style="margin:0 0 0.35rem">
            <input type="checkbox" ${item.checked ? 'checked' : ''} onchange="toggleGuideChecklist(${activeGuideStep}, ${i})">
            <span>${escapeHtml(item.text)}</span>
        </label>`
    ).join('');

    panel.innerHTML = `
        <div class="guide-progress-bar">
            <div class="guide-progress-fill" style="width:${pct}%"></div>
        </div>
        <p style="font-size:0.55rem;color:var(--base-light);margin-bottom:0.5rem">${escapeHtml(trans.guideStepLabel || 'Step')} ${activeGuideStep + 1} / ${total}${activeGuide.estimated_min ? ` · ~${activeGuide.estimated_min} ${trans.minutesLabel || 'min'}` : ''}</p>
        <h3 style="font-size:0.78rem;color:var(--accent);font-weight:normal;margin-bottom:0.35rem">${escapeHtml(step.title)}</h3>
        <p style="font-size:0.65rem;color:var(--base-light);line-height:1.45;margin-bottom:0.65rem">${escapeHtml(step.instruction)}</p>
        ${checklistHtml ? `<div class="guide-checklist">${checklistHtml}</div>` : ''}
        ${step.tip ? `<p class="guide-tip"><span class="guide-tip-label">${escapeHtml(trans.guideTipLabel || 'Tip:')}</span> ${escapeHtml(step.tip)}</p>` : ''}
        ${step.external_url ? `<a href="${escapeHtml(step.external_url)}" target="_blank" rel="noopener" class="guide-link">${escapeHtml(trans.openOfficialPage || 'Open official page')}</a>` : ''}
        ${sourcesHtml}
    `;

    document.getElementById('guideWalkthroughTitle').innerText = activeGuide.title;
    document.getElementById('guidePrevBtn').disabled = activeGuideStep === 0;
    document.getElementById('guideNextBtn').innerText = activeGuideStep >= total - 1
        ? (trans.guideFinish || 'Finish')
        : (trans.guideNext || 'Next');
}

function onGuideNextClick() {
    if (!activeGuide) return;
    if (activeGuideStep >= activeGuide.steps.length - 1) {
        closeGuideWalkthrough();
        return;
    }
    guideNextStep();
}

async function loadGuidesForTask(taskId, containerEl) {
    if (!containerEl || !taskId) return;
    const trans = (window.uiTranslations && window.uiTranslations[currentLang]) || {};
    try {
        const res = await fetch(`/api/knowledge/for-task?task_id=${encodeURIComponent(taskId)}&lang=${encodeURIComponent(currentLang)}`);
        const data = await res.json();
        const guides = data.bundle?.guides || [];
        if (!guides.length) {
            containerEl.innerHTML = '';
            return;
        }
        containerEl.innerHTML = `<div class="detail-label">${escapeHtml(trans.serviceGuidesTitle || 'Step-by-step guides')}</div>` +
            guides.map(g => `
                <button type="button" onclick="openGuideWalkthrough('${g.id}')" class="guide-launch-btn">
                    <div class="guide-launch-title">${escapeHtml(g.title)}</div>
                    <div class="guide-launch-meta">${g.step_count} ${trans.guideStepsWord || 'steps'}${g.estimated_min ? ` · ~${g.estimated_min} ${trans.minutesLabel || 'min'}` : ''}</div>
                </button>
            `).join('');
    } catch (e) {
        console.warn('guides load failed', e);
        containerEl.innerHTML = '';
    }
}

window.openGuideWalkthrough = openGuideWalkthrough;
window.closeGuideWalkthrough = closeGuideWalkthrough;
window.guidePrevStep = guidePrevStep;
window.onGuideNextClick = onGuideNextClick;
window.toggleGuideChecklist = toggleGuideChecklist;
window.loadGuidesForTask = loadGuidesForTask;
