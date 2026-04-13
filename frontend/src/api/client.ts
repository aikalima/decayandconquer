import type { PredictionParams, PredictionResponse } from "../types/prediction";

const API_BASE = "http://localhost:6173";

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ToolResult {
  tool: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
}

export interface ChatResponse {
  response: string;
  tool_results: ToolResult[];
}

export type ChatProvider = "google" | "anthropic";

export async function sendChatMessage(
  messages: ChatMessage[],
  provider: ChatProvider = "google",
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, provider }),
    signal,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Chat error: ${res.status}`);
  }
  return res.json();
}

export async function fetchPrediction(
  params: PredictionParams
): Promise<PredictionResponse> {
  const qs = new URLSearchParams({
    ticker: params.ticker,
    obs_date_from: params.obs_date_from,
    obs_date_to: params.obs_date_to,
    target_date: params.target_date,
    risk_free_rate: String(params.risk_free_rate),
    solver: params.solver,
    kernel_smooth: String(params.kernel_smooth),
  });

  const res = await fetch(`${API_BASE}/predict?${qs}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export interface ProgressEvent {
  stage?: string;
  progress: number;
  done?: boolean;
  result?: PredictionResponse;
  error?: string;
}

export async function fetchPredictionStream(
  params: PredictionParams,
  onProgress: (event: ProgressEvent) => void
): Promise<PredictionResponse> {
  const qs = new URLSearchParams({
    ticker: params.ticker,
    obs_date_from: params.obs_date_from,
    obs_date_to: params.obs_date_to,
    target_date: params.target_date,
    risk_free_rate: String(params.risk_free_rate),
    solver: params.solver,
    kernel_smooth: String(params.kernel_smooth),
  });

  const res = await fetch(`${API_BASE}/predict-stream?${qs}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: PredictionResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6);
      try {
        const event: ProgressEvent = JSON.parse(payload);
        if (event.error) throw new Error(event.error);
        onProgress(event);
        if (event.done && event.result) finalResult = event.result;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }

  if (!finalResult) throw new Error("Stream ended without a result");
  return finalResult;
}

// ---------------------------------------------------------------------------
// Market Context
// ---------------------------------------------------------------------------

export interface MarketEvent {
  date: string;
  headline: string;
  category: "earnings" | "macro" | "geopolitical" | "sector" | "company" | "regulatory";
  impact: string;
  source?: string;
}

export interface MarketContextResponse {
  events: MarketEvent[];
  disclaimer: string;
}

export async function fetchMarketContext(
  ticker: string,
  obsFrom: string,
  obsTo: string,
): Promise<MarketContextResponse> {
  const qs = new URLSearchParams({ ticker, obs_from: obsFrom, obs_to: obsTo });
  const res = await fetch(`${API_BASE}/market-context?${qs}`);
  if (!res.ok) {
    return { events: [], disclaimer: "Failed to fetch market context." };
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Theta Plays Screener
// ---------------------------------------------------------------------------

export interface ThetaPlayRow {
  ticker: string;
  spot: number;
  expiry: string;
  call_strike: number;
  call_bid: number;
  call_ask: number;
  call_mid: number;
  call_iv: number;
  put_strike: number;
  put_bid: number;
  put_ask: number;
  put_mid: number;
  put_iv: number;
  hv_20: number;
  call_premium: number;
  put_premium: number;
  avg_premium: number;
  call_efficiency: number;
  put_efficiency: number;
  beta: number;
  pct_change_5d: number;
}

export interface ThetaPlaysResponse {
  highest_premium: ThetaPlayRow[];
  expensive_calls: ThetaPlayRow[];
  expensive_puts: ThetaPlayRow[];
  scan_time_seconds: number;
  tickers_scanned: number;
  tickers_failed: string[];
  expiry: string;
  scan_id?: string;
  scanned_at?: string;
  hv_days?: number;
  error?: string;
}

export async function fetchThetaPlays(expiry?: string): Promise<ThetaPlaysResponse | null> {
  try {
    const qs = expiry ? `?expiry=${expiry}` : "";
    const res = await fetch(`${API_BASE}/theta-plays${qs}`);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return data;
  } catch {
    return null;
  }
}

export interface ThetaExpiry {
  expiry: string;
  last_scanned: string;
  tickers_scanned: number;
}

export async function fetchThetaExpiries(): Promise<ThetaExpiry[]> {
  try {
    const res = await fetch(`${API_BASE}/theta-expiries`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.expiries || [];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Options Heat Map
// ---------------------------------------------------------------------------

export interface HeatMapCell {
  strike: number;
  expiry: string;
  call_volume: number;
  put_volume: number;
  call_oi: number;
  put_oi: number;
  call_mid: number;
  put_mid: number;
  call_iv: number;
  put_iv: number;
  net_volume: number;
  net_oi: number;
  net_premium: number;
}

export interface HeatMapResponse {
  ticker: string;
  spot: number;
  expiries: string[];
  strikes: number[];
  cells: HeatMapCell[];
  fetch_time_seconds: number;
  error?: string;
}

export interface HeatMapProgressEvent {
  stage?: string;
  progress: number;
  done?: boolean;
  result?: HeatMapResponse;
  error?: string;
}

export async function fetchHeatMapStream(
  ticker: string,
  numExpiries: number,
  onProgress: (event: HeatMapProgressEvent) => void,
): Promise<HeatMapResponse> {
  const qs = new URLSearchParams({
    ticker,
    num_expiries: String(numExpiries),
  });

  const res = await fetch(`${API_BASE}/heatmap-stream?${qs}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: HeatMapResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event: HeatMapProgressEvent = JSON.parse(line.slice(6));
        if (event.error) throw new Error(event.error);
        onProgress(event);
        if (event.done && event.result) finalResult = event.result;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }

  if (!finalResult) throw new Error("Stream ended without results");
  return finalResult;
}

export interface ThetaPlaysProgressEvent {
  stage?: string;
  progress: number;
  row?: ThetaPlayRow | null;
  done?: boolean;
  results?: ThetaPlaysResponse;
  error?: string;
}

export async function fetchThetaPlaysStream(
  tickers: string,
  daysForward: number,
  onProgress: (event: ThetaPlaysProgressEvent) => void,
): Promise<ThetaPlaysResponse> {
  const qs = new URLSearchParams({
    tickers,
    days_forward: String(daysForward),
  });

  const res = await fetch(`${API_BASE}/theta-plays-stream?${qs}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: ThetaPlaysResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event: ThetaPlaysProgressEvent = JSON.parse(line.slice(6));
        if (event.error) throw new Error(event.error);
        onProgress(event);
        if (event.done && event.results) finalResult = event.results;
      } catch (e) {
        if (e instanceof SyntaxError) continue;
        throw e;
      }
    }
  }

  if (!finalResult) throw new Error("Stream ended without results");
  return finalResult;
}
