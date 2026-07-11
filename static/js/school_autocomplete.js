/**
 * Plain text inputs for school name and location.
 * TomSelect has been removed — these are now simple <input type="text"> fields
 * with no autocomplete dropdown, which works reliably on mobile.
 */

function initSchoolAutocomplete(lang) {
    // Nothing to initialise — plain input handles itself.
    // Keep function signature so callers don't break.
    const input = document.getElementById('schoolName');
    if (!input) return;
    // Prevent form submission on Enter key (mobile keyboard "Go" / "Done")
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            // Move focus to next field (arrival date)
            const next = document.getElementById('arrivalDate');
            if (next) next.focus();
        }
    });
}

function initLocationAutocomplete(lang) {
    const input = document.getElementById('location');
    if (!input) return;
    // Prevent form submission on Enter key
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const next = document.getElementById('japaneseLevel');
            if (next) next.focus();
        }
    });
}

function setSchoolFieldValue(name) {
    const el = document.getElementById('schoolName');
    if (el && name) el.value = name;
}

function setLocationFieldValue(loc) {
    const el = document.getElementById('location');
    if (el && loc) el.value = loc;
}

function getSchoolFieldValue() {
    return (document.getElementById('schoolName')?.value || '').trim();
}

function getLocationFieldValue() {
    return (document.getElementById('location')?.value || '').trim();
}

window.initSchoolAutocomplete = initSchoolAutocomplete;
window.initLocationAutocomplete = initLocationAutocomplete;
window.setSchoolFieldValue = setSchoolFieldValue;
window.setLocationFieldValue = setLocationFieldValue;
window.getSchoolFieldValue = getSchoolFieldValue;
window.getLocationFieldValue = getLocationFieldValue;
