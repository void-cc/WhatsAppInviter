import './style.css';
import { EventsOn } from '../wailsjs/runtime/runtime.js';
import * as App from '../wailsjs/go/main/App.js';

// --- State ---
let contacts = [];
let currentPage = 0;
let sentCol = '';
let stats = { sent: 0, failed: 0, total: 0, remaining: 0 };
let logStarted = false;

// --- DOM helpers ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function setStatus(text, accent = false) {
  $('#status-text').textContent = text;
  $('#status-dot').className = 'dot ' + (accent ? 'sent' : 'faint');
}

function log(msg) {
  const box = $('#log-box');
  if (!logStarted) {
    box.textContent = '';
    logStarted = true;
  }
  box.textContent += msg + '\n';
  box.scrollTop = box.scrollHeight;
}

function showPage(idx) {
  currentPage = idx;
  $$('.page').forEach((p) => p.classList.toggle('active', +p.dataset.page === idx));
  $$('.step').forEach((s) => s.classList.toggle('active', +s.dataset.page === idx));
}

function fillSelect(el, values, selected = '') {
  el.innerHTML = '';
  for (const v of values) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === selected) opt.selected = true;
    el.appendChild(opt);
  }
}

function contactLabel(i, c) {
  return `${i + 1} - ${c.name} (${c.phoneNormalized}) - Excel-rij ${c.rowIndex}`;
}

function refreshRangeOptions() {
  const labels = contacts.map((c, i) => contactLabel(i, c));
  fillSelect($('#start-select'), ['(begin)', ...labels]);
  fillSelect($('#end-select'), ['(einde)', ...labels]);
}

function resolveIndex(selected, fallback) {
  if (!selected || selected === '(begin)' || selected === '(einde)') return fallback;
  const pos = parseInt(selected.split(' - ')[0], 10);
  return isNaN(pos) ? fallback : Math.max(0, Math.min(pos - 1, contacts.length - 1));
}

function updateProgress() {
  const { sent, failed, total, remaining } = stats;
  const headline = $('#progress-headline');
  if (total === 0) {
    headline.textContent = 'Nog geen contacten geladen';
  } else if (remaining === 1) {
    headline.textContent = '1 student klaar om uit te nodigen';
  } else {
    headline.textContent = `${remaining} studenten klaar om uit te nodigen`;
  }
  $('#stat-sent').textContent = sent;
  $('#stat-remaining').textContent = remaining;
  $('#stat-failed').textContent = failed;
  $('#legend-failed').classList.toggle('hidden', failed === 0);
  const sf = total ? sent / total : 0;
  const ff = total ? failed / total : 0;
  $('#seg-sent').style.width = `${sf * 100}%`;
  $('#seg-failed').style.width = `${ff * 100}%`;
  $('#seg-failed').style.left = `${sf * 100}%`;
}

async function loadSettings() {
  const s = await App.GetSettings();
  $('#message-box').value = s.message || '';
  $('#country-code').value = s.countryCode || '+31';
  $('#wait-time').value = s.waitTime || 15;
  $('#confirm-each').checked = s.confirmEach !== false;
  $('#skip-sent').checked = s.skipSent !== false;
  $('#mark-sent').checked = s.markSent !== false;
  $('#reduced-motion').checked = !!s.reducedMotion;
  applyTheme(s.appearance === 'Donker' ? 'dark' : s.appearance === 'Licht' ? 'light' : 'system');
  updatePreview();
}

function applyTheme(mode) {
  document.documentElement.dataset.theme = mode === 'system' ? '' : mode;
  $$('.theme-btn').forEach((b) => b.classList.toggle('active', b.dataset.theme === mode));
}

async function updatePreview() {
  const r = await App.PreviewMessage($('#message-box').value.trim());
  $('#placeholder-hint').textContent = r.hint;
  $('#preview-name').textContent = r.name;
  $('#preview-text').textContent = r.preview || '—';
}

async function refreshContacts() {
  const phone = $('#phone-col').value;
  let name = $('#name-col').value;
  let sent = $('#sent-col').value;
  const cc = $('#country-code').value.trim() || '+31';
  sentCol = sent;
  const r = await App.RefreshContacts(phone, name, sent, cc);
  contacts = r.contacts || [];
  $('#contact-count').textContent = r.total || 0;
  const already = r.alreadySent || 0;
  if (sent !== '(geen)' && $('#skip-sent').checked && already) {
    $('#contact-label').textContent = `geldige nummers - ${already} al verzonden, ${r.remaining} te gaan`;
  } else {
    $('#contact-label').textContent = 'geldige telefoonnummers gevonden';
  }
  stats = { sent: 0, failed: 0, total: r.total || 0, remaining: r.remaining || 0 };
  updateProgress();
  refreshRangeOptions();
  updatePreview();
}

async function saveSettings() {
  const appearance = document.documentElement.dataset.theme === 'dark' ? 'Donker'
    : document.documentElement.dataset.theme === 'light' ? 'Licht' : 'Systeem';
  await App.SaveSettings({
    message: $('#message-box').value.trim(),
    countryCode: $('#country-code').value.trim(),
    waitTime: parseInt($('#wait-time').value, 10) || 15,
    confirmEach: $('#confirm-each').checked,
    skipSent: $('#skip-sent').checked,
    markSent: $('#mark-sent').checked,
    reducedMotion: $('#reduced-motion').checked,
    appearance,
    phoneColumn: $('#phone-col').value,
    nameColumn: $('#name-col').value === '(geen)' ? '' : $('#name-col').value,
    sentColumn: $('#sent-col').value === '(geen)' ? '' : $('#sent-col').value,
    lastSheet: $('#sheet-select').value,
  });
  alert('Instellingen opgeslagen als standaard.');
}

async function updateWAStatus() {
  const st = await App.WhatsAppLoginStatus();
  $('#wa-status-text').textContent = st.loggedIn
    ? `Gekoppeld${st.phone ? ' (' + st.phone + ')' : ''}`
    : 'Niet gekoppeld';
  $('#wa-status-dot').className = 'dot ' + (st.loggedIn ? 'sent' : 'faint');
}

// --- Event wiring ---
$('#pick-excel').addEventListener('click', async () => {
  try {
    const r = await App.PickExcel();
    if (!r) return;
    $('#file-label').textContent = r.path.split(/[/\\]/).pop();
    $('#file-label').classList.remove('muted');
    fillSelect($('#sheet-select'), r.sheets, r.sheetName);
    const none = ['(geen)'];
    fillSelect($('#phone-col'), r.headers, r.phoneCol);
    fillSelect($('#name-col'), [...none, ...r.headers], r.nameCol || '(geen)');
    fillSelect($('#sent-col'), [...none, ...r.headers], r.sentCol || '(geen)');
    sentCol = r.sentCol || '';
    log(`Geladen: ${r.path.split(/[/\\]/).pop()} / ${r.sheetName}`);
    setStatus('Excel geladen', true);
    await refreshContacts();
  } catch (e) {
    alert(String(e));
  }
});

$('#sheet-select').addEventListener('change', async (e) => {
  const r = await App.LoadSheet(e.target.value);
  fillSelect($('#phone-col'), r.headers, r.phoneCol);
  const none = ['(geen)'];
  fillSelect($('#name-col'), [...none, ...r.headers], r.nameCol || '(geen)');
  fillSelect($('#sent-col'), [...none, ...r.headers], r.sentCol || '(geen)');
  sentCol = r.sentCol || '';
  await refreshContacts();
});

['phone-col', 'name-col', 'sent-col', 'country-code'].forEach((id) => {
  $(`#${id}`).addEventListener('change', refreshContacts);
  if (id === 'country-code') $(`#${id}`).addEventListener('input', refreshContacts);
});

$('#skip-sent').addEventListener('change', refreshContacts);
$('#message-box').addEventListener('input', updatePreview);

$$('.step').forEach((s) => s.addEventListener('click', () => showPage(+s.dataset.page)));
$('#to-message').addEventListener('click', () => showPage(1));
$('#back-import').addEventListener('click', () => showPage(0));
$('#to-send').addEventListener('click', () => showPage(2));
$('#save-default').addEventListener('click', saveSettings);

$$('.theme-btn').forEach((b) => b.addEventListener('click', () => applyTheme(b.dataset.theme)));

$('#wa-pair').addEventListener('click', async () => {
  $('#qr-container').classList.remove('hidden');
  try {
    await App.WhatsAppPair();
    await updateWAStatus();
    $('#qr-container').classList.add('hidden');
  } catch (e) {
    alert(String(e));
  }
});

$('#wa-connect').addEventListener('click', async () => {
  try {
    await App.WhatsAppConnect();
    await updateWAStatus();
  } catch (e) {
    alert(String(e));
  }
});

$('#wa-logout').addEventListener('click', async () => {
  await App.WhatsAppLogout();
  await updateWAStatus();
});

$('#start-send').addEventListener('click', async () => {
  try {
    const startIdx = resolveIndex($('#start-select').value, 0);
    const endIdx = resolveIndex($('#end-select').value, contacts.length - 1);
    await App.StartSending({
      message: $('#message-box').value.trim(),
      waitTime: parseInt($('#wait-time').value, 10) || 15,
      confirmEach: $('#confirm-each').checked,
      skipSent: $('#skip-sent').checked,
      startIndex: startIdx,
      endIndex: endIdx,
    });
    logStarted = false;
    log('--- Start versturen ---');
    stats.sent = 0;
    stats.failed = 0;
    $('#start-send').disabled = true;
    $('#stop-send').classList.remove('hidden');
    setStatus('Actief', true);
  } catch (e) {
    alert(String(e));
  }
});

$('#stop-send').addEventListener('click', () => {
  App.StopSending();
  log('Stop aangevraagd…');
});

$('#continue-send').addEventListener('click', () => {
  App.ConfirmContinue();
  $('#continue-send').classList.add('hidden');
});

$('#export-report').addEventListener('click', async () => {
  try {
    const path = await App.ExportReport();
    if (path) alert(`Rapport opgeslagen:\n${path}`);
  } catch (e) {
    alert(String(e));
  }
});

EventsOn('qr-code', (code) => {
  $('#qr-code').textContent = code;
  $('#qr-container').classList.remove('hidden');
});

EventsOn('send-event', async (evt) => {
  if (evt.message) log(evt.message);

  if (evt.contact && ['SENT', 'FAILED', 'SKIPPED'].includes(evt.status)) {
    await App.RecordSendResult(evt.contact.name, evt.contact.phoneNormalized, evt.status, evt.message);
    if (evt.status === 'SENT') await App.RecordSentRow(evt.contact.rowIndex);
    if (evt.status === 'SENT') stats.sent++;
    if (evt.status === 'FAILED') stats.failed++;
    stats.remaining = Math.max(0, stats.total - stats.sent - stats.failed);
    updateProgress();
  }

  if (evt.status === 'WAITING_CONFIRM') {
    $('#continue-send').classList.remove('hidden');
    setStatus('Wacht op jou');
  }

  if (evt.status === 'STOPPED' || evt.status === 'COMPLETED') {
    $('#start-send').disabled = false;
    $('#stop-send').classList.add('hidden');
    $('#continue-send').classList.add('hidden');
    $('#export-report').disabled = false;
    setStatus('Afgerond', true);
    try {
      const n = await App.WriteBackSent(sentCol);
      if (n > 0) log(`${n} rij(en) afgevinkt in Excel.`);
    } catch (e) {
      alert('Kon Excel niet bijwerken:\n' + e);
    }
  }
});

// --- Init ---
loadSettings();
updateWAStatus();
