export interface PredictionMeta {
  ticker: string;
  obs_date: string;
  obs_date_from: string;
  obs_date_to: string;
  target_date: string;
  days_forward: number;
  days_averaged: number;
  spot: number;
  expiry_used: string;
  data_source?: string;
  realized_price?: number;
}

export interface IvSmile {
  raw_strikes: number[];
  raw_iv: number[];
  smooth_strikes: number[];
  smooth_iv: number[];
  n_strikes: number;
}

export interface PredictionResponse {
  data: {
    Price: Record<string, number>;
    PDF: Record<string, number>;
    CDF: Record<string, number>;
  };
  meta: PredictionMeta;
  iv_smile: IvSmile;
}

export interface PredictionData {
  prices: number[];
  pdf: number[];
  cdf: number[];
}

export interface PredictionParams {
  ticker: string;
  obs_date_from: string;
  obs_date_to: string;
  target_date: string;
  risk_free_rate: number;
  solver: "brent" | "newton";
  kernel_smooth: boolean;
}

export function parsePredictionResponse(raw: PredictionResponse): PredictionData {
  const keys = Object.keys(raw.data.Price)
    .map(Number)
    .sort((a, b) => a - b);
  return {
    prices: keys.map((k) => raw.data.Price[String(k)]),
    pdf: keys.map((k) => raw.data.PDF[String(k)]),
    cdf: keys.map((k) => raw.data.CDF[String(k)]),
  };
}
