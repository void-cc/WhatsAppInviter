import './style.css';
import { EventsOn } from '../wailsjs/runtime/runtime.js';
import * as App from '../wailsjs/go/main/App.js';

type Contact = {
  name: string;
  phoneNormalized: string;
  rowIndex: number;
};

type Stats = {
  sent: number;
  failed: number;
  total: number;
  remaining: number;
};

type ThemeMode = 'dark' | 'light' | 'system';

type Settings = {
  message?: string;
  country_code?: string;
  wait_time?: number;
  confirm_each?: boolean;
  skip_sent?: boolean;
  mark_sent?: boolean;
  reduced_motion?: boolean;
  appearance?: string;
  phone_column?: string;
  name_column?: string;
  sent_column?: string;
  last_sheet?: string;
};

type SendEvent = {
  status: string;
  message?: string;
  contact?: Contact;
};

type RefreshResult = {
  total?: number;
  alreadySent?: number;
  remaining?: number;
  contacts?: Contact[];
};

type SheetResult = {
  headers: string[];
  phoneCol?: string;
  nameCol?: string;
  sentCol?: string;
  sheetName?: string;
};

type PickExcelResult = SheetResult & {
  path: string;
  sheets: string[];
};

// --- State ---
let contacts: Contact[] = [];
let currentPage = 0;
let sentCol = '';
let stats: Stats = { sent: 0, failed: 0, total: 0, remaining: 0 };
let logStarted = false;

// --- DOM helpers ---
const $ = <T extends Element = Element>(sel: string): T =>
  document.querySelector(sel) as T;

const $$ = <T extends Element = Element>(sel: string): NodeListOf<T> =>
  document.querySelectorAll(sel) as NodeListOf<T>;

function setStatus(text: string, accent = false): void {
  $('#status-text').textContent = text;
  $('#status-dot').className = 'dot ' + (accent ? 'sent' : 'faint');
}

function log(msg: string): void {
  const box = $('#log-box') as HTMLPreElement;
  if (!logStarted) {
    box.textContent = '';
    logStarted = true;
  }
  box.textContent += msg + '\n';
  box.scrollTop = box.scrollHeight;
}

function showPage(idx: number): void {
  currentPage = idx;
  $$<HTMLElement>('.page').forEach((p) =>
    p.classList.toggle('active', +(p.dataset.page ?? 0) === idx),
  );
  $$<HTMLElement>('.step').forEach((s) =>
    s.classList.toggle('active', +(s.dataset.page ?? 0) === idx),
  );
}

function fillSelect(el: HTMLSelectElement, values: string[], selected = ''): void {
  el.innerHTML = '';
  for (const v of values) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === selected) opt.selected = true;
    el.appendChild(opt);
  }
}

function contactLabel(i: number, c: Contact): string {
  return `${i + 1} - ${c.name} (${c.phoneNormalized}) - Excel-rij ${c.rowIndex}`;
}

function refreshRangeOptions(): void {
  const labels = contacts.map((c, i) => contactLabel(i, c));
  fillSelect($('#start-select') as HTMLSelectElement, ['(begin)', ...labels]);
  fillSelect($('#end-select') as HTMLSelectElement, ['(einde)', ...labels]);
}

function resolveIndex(selected: string, fallback: number): number {
  if (!selected || selected === '(begin)' || selected === '(einde)') return fallback;
  const pos = parseInt(selected.split(' - ')[0], 10);
  return isNaN(pos) ? fallback : Math.max(0, Math.min(pos - 1, contacts.length - 1));
}

function updateProgress(): void {
  const { sent, failed, total, remaining } = stats;
  const headline = $('#progress-headline');
  if (total === 0) {
    headline.textContent = 'Nog geen contacten geladen';
  } else if (remaining === 1) {
    headline.textContent = '1 student klaar om uit te nodigen';
  } else {
    headline.textContent = `${remaining} studenten klaar om uit te nodigen`;
  }
  $('#stat-sent').textContent = String(sent);
  $('#stat-remaining').textContent = String(remaining);
  $('#stat-failed').textContent = String(failed);
  $('#legend-failed').classList.toggle('hidden', failed === 0);
  const sf = total ? sent / total : 0;
  const ff = total ? failed / total : 0;
  ($('#seg-sent') as HTMLElement).style.width = `${sf * 100}%`;
  const failedSeg = $('#seg-failed') as HTMLElement;
  failedSeg.style.width = `${ff * 100}%`;
  failedSeg.style.left = `${sf * 100}%`;
}

async function loadSettings(): Promise<void> {
  const s = (await App.GetSettings()) as Settings;
  ($('#message-box') as HTMLTextAreaElement).value = s.message || '';
  ($('#country-code') as HTMLInputElement).value = s.country_code || '+31';
  ($('#wait-time') as HTMLInputElement).value = String(s.wait_time ?? 15);
  ($('#confirm-each') as HTMLInputElement).checked = s.confirm_each !== false;
  ($('#skip-sent') as HTMLInputElement).checked = s.skip_sent !== false;
  ($('#mark-sent') as HTMLInputElement).checked = s.mark_sent !== false;
  ($('#reduced-motion') as HTMLInputElement).checked = !!s.reduced_motion;
  applyTheme(
    s.appearance === 'Donker' ? 'dark' : s.appearance === 'Licht' ? 'light' : 'system',
  );
  await updatePreview();
}

function applyTheme(mode: ThemeMode): void {
  document.documentElement.dataset.theme = mode === 'system' ? '' : mode;
  $$<HTMLElement>('.theme-btn').forEach((b) =>
    b.classList.toggle('active', b.dataset.theme === mode),
  );
}

async function updatePreview(): Promise<void> {
  const r = await App.PreviewMessage(($('#message-box') as HTMLTextAreaElement).value.trim());
  $('#placeholder-hint').textContent = r.hint;
  $('#preview-name').textContent = r.name;
  $('#preview-text').textContent = r.preview || '—';
}

async function refreshContacts(): Promise<void> {
  const phone = ($('#phone-col') as HTMLSelectElement).value;
  const name = ($('#name-col') as HTMLSelectElement).value;
  const sent = ($('#sent-col') as HTMLSelectElement).value;
  const cc = ($('#country-code') as HTMLInputElement).value.trim() || '+31';
  sentCol = sent;
  const r = (await App.RefreshContacts(phone, name, sent, cc)) as RefreshResult;
  contacts = r.contacts || [];
  $('#contact-count').textContent = String(r.total || 0);
  const already = r.alreadySent || 0;
  if (sent !== '(geen)' && ($('#skip-sent') as HTMLInputElement).checked && already) {
    $('#contact-label').textContent =
      `geldige nummers - ${already} al verzonden, ${r.remaining} te gaan`;
  } else {
    $('#contact-label').textContent = 'geldige telefoonnummers gevonden';
  }
  stats = { sent: 0, failed: 0, total: r.total || 0, remaining: r.remaining || 0 };
  updateProgress();
  refreshRangeOptions();
  await updatePreview();
}

async function saveSettings(): Promise<void> {
  const appearance =
    document.documentElement.dataset.theme === 'dark'
      ? 'Donker'
      : document.documentElement.dataset.theme === 'light'
        ? 'Licht'
        : 'Systeem';
  await App.SaveSettings({
    message: ($('#message-box') as HTMLTextAreaElement).value.trim(),
    country_code: ($('#country-code') as HTMLInputElement).value.trim(),
    wait_time: parseInt(($('#wait-time') as HTMLInputElement).value, 10) || 15,
    confirm_each: ($('#confirm-each') as HTMLInputElement).checked,
    skip_sent: ($('#skip-sent') as HTMLInputElement).checked,
    mark_sent: ($('#mark-sent') as HTMLInputElement).checked,
    reduced_motion: ($('#reduced-motion') as HTMLInputElement).checked,
    appearance,
    phone_column: ($('#phone-col') as HTMLSelectElement).value,
    name_column:
      ($('#name-col') as HTMLSelectElement).value === '(geen)'
        ? ''
        : ($('#name-col') as HTMLSelectElement).value,
    sent_column:
      ($('#sent-col') as HTMLSelectElement).value === '(geen)'
        ? ''
        : ($('#sent-col') as HTMLSelectElement).value,
    last_sheet: ($('#sheet-select') as HTMLSelectElement).value,
  });
  alert('Instellingen opgeslagen als standaard.');
}

async function updateWAStatus(): Promise<void> {
  const st = await App.WhatsAppLoginStatus();
  $('#wa-status-text').textContent = st.loggedIn
    ? `Gekoppeld${st.phone ? ' (' + st.phone + ')' : ''}`
    : 'Niet gekoppeld';
  $('#wa-status-dot').className = 'dot ' + (st.loggedIn ? 'sent' : 'faint');
}

// --- Event wiring ---
$('#pick-excel').addEventListener('click', async () => {
  try {
    const r = (await App.PickExcel()) as PickExcelResult | null;
    if (!r) return;
    $('#file-label').textContent = r.path.split(/[/\\]/).pop() ?? '';
    $('#file-label').classList.remove('muted');
    fillSelect($('#sheet-select') as HTMLSelectElement, r.sheets, r.sheetName);
    const none = ['(geen)'];
    fillSelect($('#phone-col') as HTMLSelectElement, r.headers, r.phoneCol);
    fillSelect($('#name-col') as HTMLSelectElement, [...none, ...r.headers], r.nameCol || '(geen)');
    fillSelect($('#sent-col') as HTMLSelectElement, [...none, ...r.headers], r.sentCol || '(geen)');
    sentCol = r.sentCol || '';
    log(`Geladen: ${r.path.split(/[/\\]/).pop()} / ${r.sheetName}`);
    setStatus('Excel geladen', true);
    await refreshContacts();
  } catch (e) {
    alert(String(e));
  }
});

$('#sheet-select').addEventListener('change', async (e: Event) => {
  const target = e.target as HTMLSelectElement;
  const r = (await App.LoadSheet(target.value)) as SheetResult;
  fillSelect($('#phone-col') as HTMLSelectElement, r.headers, r.phoneCol);
  const none = ['(geen)'];
  fillSelect($('#name-col') as HTMLSelectElement, [...none, ...r.headers], r.nameCol || '(geen)');
  fillSelect($('#sent-col') as HTMLSelectElement, [...none, ...r.headers], r.sentCol || '(geen)');
  sentCol = r.sentCol || '';
  await refreshContacts();
});

(['phone-col', 'name-col', 'sent-col', 'country-code'] as const).forEach((id) => {
  $(`#${id}`).addEventListener('change', () => void refreshContacts());
  if (id === 'country-code') {
    $(`#${id}`).addEventListener('input', () => void refreshContacts());
  }
});

$('#skip-sent').addEventListener('change', () => void refreshContacts());
$('#message-box').addEventListener('input', () => void updatePreview());

$$<HTMLElement>('.step').forEach((s) =>
  s.addEventListener('click', () => showPage(+(s.dataset.page ?? 0))),
);
$('#to-message').addEventListener('click', () => showPage(1));
$('#back-import').addEventListener('click', () => showPage(0));
$('#to-send').addEventListener('click', () => showPage(2));
$('#save-default').addEventListener('click', () => void saveSettings());

$$<HTMLElement>('.theme-btn').forEach((b) =>
  b.addEventListener('click', () => applyTheme((b.dataset.theme ?? 'system') as ThemeMode)),
);

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
    const startIdx = resolveIndex(($('#start-select') as HTMLSelectElement).value, 0);
    const endIdx = resolveIndex(
      ($('#end-select') as HTMLSelectElement).value,
      contacts.length - 1,
    );
    await App.StartSending({
      message: ($('#message-box') as HTMLTextAreaElement).value.trim(),
      waitTime: parseInt(($('#wait-time') as HTMLInputElement).value, 10) || 15,
      confirmEach: ($('#confirm-each') as HTMLInputElement).checked,
      skipSent: ($('#skip-sent') as HTMLInputElement).checked,
      startIndex: startIdx,
      endIndex: endIdx,
    });
    logStarted = false;
    log('--- Start versturen ---');
    stats.sent = 0;
    stats.failed = 0;
    ($('#start-send') as HTMLButtonElement).disabled = true;
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

EventsOn('qr-code', (code: unknown) => {
  $('#qr-code').textContent = String(code);
  $('#qr-container').classList.remove('hidden');
});

EventsOn('send-event', async (raw: unknown) => {
  const evt = raw as SendEvent;
  if (evt.message) log(evt.message);

  if (evt.contact && ['SENT', 'FAILED', 'SKIPPED'].includes(evt.status)) {
    await App.RecordSendResult(
      evt.contact.name,
      evt.contact.phoneNormalized,
      evt.status,
      evt.message ?? '',
    );
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
    ($('#start-send') as HTMLButtonElement).disabled = false;
    $('#stop-send').classList.add('hidden');
    $('#continue-send').classList.add('hidden');
    ($('#export-report') as HTMLButtonElement).disabled = false;
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
void loadSettings();
void updateWAStatus();
