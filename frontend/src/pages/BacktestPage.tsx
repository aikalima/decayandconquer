import { useState, useEffect, useRef } from "react";
import Tutorial, { startTutorial } from "../components/Tutorial";
import PredictionForm, { DEFAULTS } from "../components/PredictionForm";
import PdfChart from "../components/PdfChart";
import CdfChart from "../components/CdfChart";
import IvSmileChart from "../components/IvSmileChart";
import GreeksChart from "../components/GreeksChart";
import RiskGauge from "../components/RiskGauge";
import SummaryStats, { getAccuracyBadge, interpCdfAt } from "../components/SummaryStats";
import ProgressBar from "../components/ProgressBar";
import { fetchPredictionStream } from "../api/client";
import type { PredictionParams, PredictionData, PredictionMeta, IvSmile, Greeks } from "../types/prediction";
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
  const [ivSmile, setIvSmile] = useState<IvSmile | null>(null);
  const [greeks, setGreeks] = useState<Greeks | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [ciLevel, setCiLevel] = useState<50 | 90>(90);
  const [showExplainer, setShowExplainer] = useState(false);

  const handleSubmit = async (p: PredictionParams) => {
    setLoading(true);
    setError(null);
    setData(null);
    setMeta(null);
    setIvSmile(null);
    setGreeks(null);
    setProgress(0);
    setStage("Starting...");

    try {
      const raw = await fetchPredictionStream(p, (event) => {
        if (event.stage) setStage(event.stage);
        setProgress(event.progress);
      });
      setData(parsePredictionResponse(raw));
      setMeta(raw.meta);
      setIvSmile(raw.iv_smile);
      setGreeks(raw.greeks);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setData(null);
      setMeta(null);
      setIvSmile(null);
      setGreeks(null);
    } finally {
      setLoading(false);
    }
  };

  // Auto-run with defaults on first load
  const didAutoRun = useRef(false);
  useEffect(() => {
    if (didAutoRun.current) return;
    didAutoRun.current = true;
    handleSubmit({
      ticker: "SPY",
      obs_date_from: DEFAULTS.obsFrom,
      obs_date_to: DEFAULTS.obsTo,
      target_date: DEFAULTS.target,
      risk_free_rate: 0.04,
      solver: "brent",
      kernel_smooth: false,
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const median = data ? computeMedian(data) : 0;
  const isPrediction = meta ? !meta.realized_price : false;
  const modeLabel = isPrediction ? "Prediction" : "Backtest";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Tutorial />
      <div>
        <p style={{ margin: 0, fontSize: 13, color: "#888", lineHeight: 1.6, maxWidth: "60%" }}>
          Predict where a stock is headed by reverse-engineering probability distributions
          from 90 million+ options data points.
          {" "}
          <span
            onClick={() => setShowExplainer(true)}
            style={{ color: "#2ecc71", cursor: "pointer", fontWeight: 700, fontSize: 13 }}
          >
            Explain how it works
          </span>
          <br />
          Set a target in the past to backtest against the actual price,
          or set a future target to predict.
          {" "}
          <span
            onClick={startTutorial}
            style={{ color: "#f1c40f", cursor: "pointer", fontWeight: 600 }}
          >
            Show me how
          </span>
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

          {/* Cards row */}
          {(() => {
            const cdfPct = meta.realized_price != null
              ? interpCdfAt(meta.realized_price, data.prices, data.cdf)
              : null;
            const badge = cdfPct != null ? getAccuracyBadge(cdfPct) : null;
            const hasRealized = meta.realized_price != null && badge && cdfPct != null;
            return (
              <div style={{ display: "grid", gridTemplateColumns: hasRealized ? "repeat(auto-fit, minmax(250px, 1fr))" : "repeat(auto-fit, minmax(300px, 1fr))", gap: 12 }}>
                {hasRealized ? (
                  <>
                    {/* Backtest Result card */}
                    <div style={{
                      background: "#1a2e1a",
                      border: "1px solid #2a5a2a",
                      borderRadius: 8,
                      padding: 12,
                      fontSize: 13,
                      color: "#aaa",
                      lineHeight: 1.6,
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "center",
                    }}>
                      <strong style={{ color: "#2ecc71", fontSize: 14 }}>Backtest Result</strong>
                      <div style={{ marginTop: 6, fontSize: 12 }}>
                        Predicted <strong style={{ color: "#ccc" }}>${median.toFixed(0)}</strong>,
                        actual was <strong style={{ color: "#2ecc71" }}>${meta.realized_price!.toFixed(2)}</strong>
                      </div>
                    </div>

                    {/* Accuracy badge card */}
                    <div style={{
                      background: badge!.bg,
                      border: `1px solid ${badge!.color}33`,
                      borderRadius: 8,
                      padding: 12,
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                          background: badge!.color,
                          color: "#000",
                          fontWeight: 700,
                          fontSize: 11,
                          padding: "2px 8px",
                          borderRadius: 4,
                        }}>
                          {badge!.label}
                        </span>
                        <span style={{ color: badge!.color, fontWeight: 600, fontSize: 13 }}>
                          CDF: {(cdfPct! * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "#bbb", lineHeight: 1.5 }}>
                        {badge!.explanation}
                      </div>
                    </div>
                  </>
                ) : (
                  /* Prediction card (no realized price) */
                  <div style={{
                    background: "#1a2e2e",
                    border: "1px solid #2a5a5a",
                    borderRadius: 8,
                    padding: 12,
                    fontSize: 13,
                    color: "#aaa",
                    lineHeight: 1.6,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                  }}>
                    <strong style={{ color: "#2ecc71", fontSize: 14 }}>Prediction</strong>
                    <div style={{ marginTop: 6, fontSize: 12 }}>
                      Given option prices from {meta.obs_date_from} to {meta.obs_date_to}, the
                      market predicts {meta.ticker} around <strong style={{ color: "#ccc" }}>${median.toFixed(0)}</strong> by {meta.target_date}.
                    </div>
                  </div>
                )}

                {/* Risk Gauge card */}
                <RiskGauge data={data} spot={meta.spot} predicted={median} realized={meta.realized_price} />
              </div>
            );
          })()}

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "#888" }}>Confidence Interval:</span>
            {([50, 90] as const).map((level) => (
              <button
                key={level}
                onClick={() => setCiLevel(level)}
                style={{
                  padding: "4px 12px",
                  borderRadius: 4,
                  border: `1px solid ${ciLevel === level ? "#6c63ff" : "#333"}`,
                  background: ciLevel === level ? "#6c63ff" : "transparent",
                  color: ciLevel === level ? "#fff" : "#888",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {level}%
              </button>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: 20 }}>
            <PdfChart key={`pdf-${meta.obs_date}-${meta.target_date}-${ciLevel}`} data={data} spot={meta.spot} realized={isPrediction ? undefined : meta.realized_price} predicted={median} ciLevel={ciLevel} />
            <CdfChart key={`cdf-${meta.obs_date}-${meta.target_date}-${ciLevel}`} data={data} spot={meta.spot} realized={isPrediction ? undefined : meta.realized_price} predicted={median} ciLevel={ciLevel} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: 20 }}>
            {ivSmile && (
              <IvSmileChart ivSmile={ivSmile} spot={meta.spot} />
            )}
            {greeks && (
              <GreeksChart greeks={greeks} spot={meta.spot} />
            )}
          </div>
        </>
      )}
      {showExplainer && <ExplainerModal onClose={() => setShowExplainer(false)} />}
    </div>
  );
}

function ExplainerModal({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.7)",
          zIndex: 10000,
        }}
      />
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "#12122a",
          border: "1px solid #2a2a4a",
          borderRadius: 16,
          padding: "32px 36px",
          maxWidth: 640,
          width: "90vw",
          maxHeight: "80vh",
          overflowY: "auto",
          zIndex: 10001,
          boxShadow: "0 16px 64px rgba(0,0,0,0.8)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 20, color: "#fff" }}>How It Works</h2>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#666",
              fontSize: 22,
              cursor: "pointer",
              padding: "0 4px",
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20, fontSize: 14, color: "#ccc", lineHeight: 1.7 }}>
          <Section title="The Idea">
            Option prices encode the market's collective expectation of where a stock will be
            on a future date. This tool reverses the Black-Scholes pricing model to extract
            the risk-neutral probability distribution hidden in those prices, turning option
            premiums back into a full forecast of future price outcomes.
          </Section>

          <Section title="The Approach">
            Black-Scholes normally takes volatility in and gives a price out. We reverse it:
            given market prices across many strikes, we solve for the implied volatility at
            each one, producing the IV smile. That curve is smoothed with a cubic B-spline,
            then we reprice options on a dense grid and take the second derivative with respect
            to strike (Breeden-Litzenberger) to recover the risk-neutral probability
            distribution of the stock's future price.
          </Section>

          <Section title="Why It's Useful">
            <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "#fff" }}>See the full picture</strong>: not just a
                point estimate, but the entire range of outcomes the market is pricing in.
              </li>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "#fff" }}>Quantify tail risk</strong>: understand the
                probability of extreme moves that simple models miss.
              </li>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "#fff" }}>Backtest accuracy</strong>: set a past target
                date and compare the predicted distribution against what actually happened.
              </li>
              <li>
                <strong style={{ color: "#fff" }}>Market consensus</strong>: this reflects the
                aggregate view of all options traders, not a single analyst's opinion.
              </li>
            </ul>
          </Section>

          <Section title="Data Pipeline">
            The system fetches options chain snapshots from the Massive API, validates
            the data, computes implied volatility for each strike, fits a B-spline to
            the IV smile, and derives the probability density via finite differences,
            all in a few seconds. When an observation window spans multiple days, IVs
            are averaged across dates before fitting.
          </Section>
        </div>

        <button
          onClick={onClose}
          style={{
            marginTop: 24,
            padding: "10px 28px",
            borderRadius: 8,
            border: "none",
            background: "#2ecc71",
            color: "#000",
            cursor: "pointer",
            fontSize: 14,
            fontWeight: 700,
            display: "block",
            marginLeft: "auto",
          }}
        >
          Got it
        </button>
      </div>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 style={{ margin: "0 0 6px", fontSize: 15, color: "#2ecc71", fontWeight: 700 }}>{title}</h3>
      <div>{children}</div>
    </div>
  );
}
