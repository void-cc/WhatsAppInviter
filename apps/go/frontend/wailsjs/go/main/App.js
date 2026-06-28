// @ts-nocheck
/* Hand-written Wails bindings for App struct */

const go = () => window.go?.main?.App;

export function GetSettings() { return go()?.GetSettings(); }
export function SaveSettings(s) { return go()?.SaveSettings(s); }
export function PickExcel() { return go()?.PickExcel(); }
export function LoadSheet(name) { return go()?.LoadSheet(name); }
export function RefreshContacts(phone, name, sent, cc) { return go()?.RefreshContacts(phone, name, sent, cc); }
export function PreviewMessage(t) { return go()?.PreviewMessage(t); }
export function WhatsAppLoginStatus() { return go()?.WhatsAppLoginStatus(); }
export function WhatsAppPair() { return go()?.WhatsAppPair(); }
export function WhatsAppConnect() { return go()?.WhatsAppConnect(); }
export function WhatsAppLogout() { return go()?.WhatsAppLogout(); }
export function StartSending(opts) { return go()?.StartSending(opts); }
export function StopSending() { return go()?.StopSending(); }
export function ConfirmContinue() { return go()?.ConfirmContinue(); }
export function RecordSendResult(n, p, s, d) { return go()?.RecordSendResult(n, p, s, d); }
export function RecordSentRow(r) { return go()?.RecordSentRow(r); }
export function GetSendResults() { return go()?.GetSendResults(); }
export function ExportReport() { return go()?.ExportReport(); }
export function WriteBackSent(col) { return go()?.WriteBackSent(col); }
