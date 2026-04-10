import type { PredictionParams, PredictionResponse } from "../types/prediction";

const API_BASE = "http://localhost:6173";

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
