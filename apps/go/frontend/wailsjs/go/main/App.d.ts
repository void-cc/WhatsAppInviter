export function GetSettings(): Promise<Record<string, unknown>>;
export function SaveSettings(s: Record<string, unknown>): Promise<void>;
export function PickExcel(): Promise<Record<string, unknown> | null>;
export function LoadSheet(name: string): Promise<Record<string, unknown>>;
export function RefreshContacts(
  phone: string,
  name: string,
  sent: string,
  cc: string,
): Promise<Record<string, unknown>>;
export function PreviewMessage(t: string): Promise<{ hint: string; name: string; preview: string }>;
export function WhatsAppLoginStatus(): Promise<{ loggedIn: boolean; phone: string }>;
export function WhatsAppPair(): Promise<void>;
export function WhatsAppConnect(): Promise<void>;
export function WhatsAppLogout(): Promise<void>;
export function StartSending(opts: Record<string, unknown>): Promise<void>;
export function StopSending(): void;
export function ConfirmContinue(): void;
export function RecordSendResult(n: string, p: string, s: string, d: string): Promise<void>;
export function RecordSentRow(r: number): Promise<void>;
export function ExportReport(): Promise<string>;
export function WriteBackSent(col: string): Promise<number>;
