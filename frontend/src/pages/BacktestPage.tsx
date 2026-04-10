import { useState } from "react";
import PredictionForm from "../components/PredictionForm";
import PdfChart from "../components/PdfChart";
import CdfChart from "../components/CdfChart";
import SummaryStats from "../components/SummaryStats";
import ProgressBar from "../components/ProgressBar";
import { fetchPredictionStream } from "../api/client";
import type { PredictionParams, PredictionData, PredictionMeta } from "../types/prediction";
import { parsePredictionResponse } from "../types/prediction";

function computeMedian(data: PredictionData): number {
  const { prices, cdf } = data;
  for (let i = 1; i < cdf.length; i++) {
    if (cdf[i] >= 0.5) {
      const t = (0.5 - cdf[i - 1]) / (cdf[i] - cdf[i - 1]);
      return prices[i - 1] + t * (prices[i] - prices[i - 1]);
    }
  }
  return prices[prices.length - 1];
}

export default function BacktestPage() {
  const [data, setData] = useState<PredictionData | null>(null);
  const [meta, setMeta] = useState<PredictionMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");

  const handleSubmit = async (p: PredictionParams) => {
    setLoading(true);
    setError(null);
    setData(null);
    setMeta(null);
    setProgress(0);
    setStage("Starting...");

    try {
      const raw = await fetchPredictionStream(p, (event) => {
        if (event.stage) setStage(event.stage);
        setProgress(event.progress);
      });
      setData(parsePredictionResponse(raw));
      setMeta(raw.meta);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setData(null);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ margin: "0 0 8px", fontSize: 20 }}>Backtest</h2>
        <p style={{ margin: "0 0 6px", fontSize: 13, color: "#aaa", lineHeight: 1.6, maxWidth: 800 }}>
          This tool extracts the market's implied probability distribution of a stock's future price
          from a single day's options chain. On any given day, call options are priced at every strike
          — cheap deep-OTM calls mean the market thinks that price is unlikely, expensive ITM calls
          mean it's almost certain. The algorithm inverts Black-Scholes across all strikes to recover
          the full probability curve.
        </p>
        <p style={{ margin: 0, fontSize: 13, color: "#888", lineHeight: 1.6, maxWidth: 800 }}>
          For backtesting: pick a past <strong style={{ color: "#bbb" }}>Observation Date</strong> (when
          to snapshot the options market) and a <strong style={{ color: "#bbb" }}>Target Date</strong> (the
          expiration those options are pricing). The pipeline extracts what the market believed the
          price distribution would be, then compares it against the actual realized price on the target
          date.
        </p>
      </div>

      <PredictionForm onSubmit={handleSubmit} loading={loading} />

      {loading && <ProgressBar progress={progress} stage={stage} />}

      {error && (
        <div
          style={{
            background: "#2e1a1a",
            border: "1px solid #5a2020",
            borderRadius: 8,
            padding: 12,
            color: "#e74c3c",
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {data && meta && (
        <>
          <SummaryStats data={data} meta={meta} />

          {meta.realized_price != null && (
            <div style={{
              background: "#1a2e1a",
              border: "1px solid #2a5a2a",
              borderRadius: 8,
              padding: 12,
              fontSize: 13,
              color: "#aaa",
              lineHeight: 1.6,
            }}>
              <strong style={{ color: "#2ecc71" }}>Backtest result: </strong>
              On {meta.obs_date}, the options market predicted {meta.ticker} would
              most likely be around <strong style={{ color: "#ccc" }}>${data.prices[data.pdf.indexOf(Math.max(...data.pdf))].toFixed(0)}</strong> by {meta.target_date}.
              The actual price was <strong style={{ color: "#2ecc71" }}>${meta.realized_price.toFixed(2)}</strong>.
              The green line on the charts shows where reality landed relative to the prediction.
            </div>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 20,
            }}
          >
            <PdfChart key={`pdf-${meta.obs_date}-${meta.target_date}`} data={data} spot={meta.spot} realized={meta.realized_price} predicted={computeMedian(data)} />
            <CdfChart key={`cdf-${meta.obs_date}-${meta.target_date}`} data={data} spot={meta.spot} realized={meta.realized_price} predicted={computeMedian(data)} />
          </div>
        </>
      )}
    </div>
  );
}
