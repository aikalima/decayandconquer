const API_BASE = import.meta.env.VITE_API_BASE || "";

export interface AiSession {
  user: { email: string; expires_at: number };
  usage: {
    your_daily_requests: number;
    your_monthly_requests: number;
    your_reported_total_tokens: number;
    daily_requests: number;
    monthly_requests: number;
    limits: { per_user_daily: number; per_user_monthly: number; daily: number; monthly: number };
  };
}

let credential = "";
let session: AiSession | null = null;
let expiryTimer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

export const getAiSession = () => session;
export function subscribeAiSession(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function signOutAi() {
  credential = "";
  session = null;
  clearTimeout(expiryTimer);
  listeners.forEach((listener) => listener());
}

export async function signInAi(token: string) {
  const response = await fetch(`${API_BASE}/ai-access/status`, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Google sign-in failed.");
  credential = token;
  session = body as AiSession;
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(signOutAi, Math.max(0, session.user.expires_at * 1000 - Date.now()));
  listeners.forEach((listener) => listener());
}

export async function refreshAiUsage() {
  const token = credential;
  if (!token) return;
  try {
    const response = await fetch(`${API_BASE}/ai-access/status`, {
      headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
    });
    if (credential !== token) return;
    if (response.status === 401) { signOutAi(); return; }
    if (!response.ok) return;
    const body = await response.json();
    if (credential !== token) return;
    session = body;
    listeners.forEach((listener) => listener());
  } catch { /* A status refresh must not discard a completed AI response. */ }
}

export async function paidAiFetch(path: string, init?: RequestInit) {
  if (!credential || !session || session.user.expires_at * 1000 <= Date.now()) {
    signOutAi();
    throw new Error("Sign in with Google using AI access in the header to use this feature.");
  }
  const token = credential;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  try {
    const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
    if (response.status === 401 && credential === token) signOutAi();
    return response;
  } finally {
    void refreshAiUsage();
  }
}

export async function fetchAiConfig(): Promise<{ client_id: string; configured: boolean }> {
  const response = await fetch(`${API_BASE}/ai-access/config`, { cache: "no-store" });
  if (!response.ok) throw new Error("AI sign-in is temporarily unavailable.");
  return response.json();
}
