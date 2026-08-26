import { useState, useEffect, useRef } from "react";
import Tutorial from "../components/Tutorial";
import { startTutorial } from "../components/tutorialController";
import PredictionForm, { DEFAULTS } from "../components/PredictionForm";
import PdfChart from "../components/PdfChart";
import CdfChart from "../components/CdfChart";
import IvSmileChart from "../components/IvSmileChart";
import GreeksChart from "../components/GreeksChart";
import HeatMapSection from "../components/HeatMapSection";
import MarketContext from "../components/MarketContext";
import SummaryStats from "../components/SummaryStats";
import ProgressBar from "../components/ProgressBar";
import { fetchPredictionStream, fetchMarketContext, fetchAppDefaults } from "../api/client";
import type { AppDefaultsResponse, MarketEvent } from "../api/client";
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
  const [marketEvents, setMarketEvents] = useState<MarketEvent[]>([]);
  const [marketDisclaimer, setMarketDisclaimer] = useState("");
  const [marketLoading, setMarketLoading] = useState(false);
  const [hoveredEventIndex, setHoveredEventIndex] = useState<number | null>(null);
  const [appDefaults, setAppDefaults] = useState<AppDefaultsResponse | null>(null);
  const [defaultsReady, setDefaultsReady] = useState(false);

  const handleSubmit = async (p: PredictionParams) => {
    setLoading(true);
    setError(null);
    setData(null);
    setMeta(null);
    setIvSmile(null);
    setGreeks(null);
    setProgress(0);
    setStage("Working...");

    // Fetch market context in parallel (non-blocking)
    setMarketLoading(true);
    setMarketEvents([]);
    fetchMarketContext(p.ticker, p.obs_date_from, p.obs_date_to)
      .then((ctx) => {
        setMarketEvents(ctx.events);
        setMarketDisclaimer(ctx.disclaimer);
      })
      .catch(() => {
        setMarketEvents([]);
        setMarketDisclaimer("Failed to fetch market context.");
      })
      .finally(() => setMarketLoading(false));

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

  useEffect(() => {
    let cancelled = false;

    fetchAppDefaults()
      .then((defaults) => {
        if (!cancelled) setAppDefaults(defaults);
      })
      .finally(() => {
        if (!cancelled) setDefaultsReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const predictionDefaults = appDefaults?.prediction ?? DEFAULTS;

  // Auto-run with defaults on first load
  const didAutoRun = useRef(false);
  useEffect(() => {
    if (!defaultsReady || didAutoRun.current) return;
    didAutoRun.current = true;
    handleSubmit({
      ticker: predictionDefaults.ticker,
      obs_date_from: predictionDefaults.obs_date_from,
      obs_date_to: predictionDefaults.obs_date_to,
      target_date: predictionDefaults.target_date,
      risk_free_rate: predictionDefaults.risk_free_rate,
      solver: predictionDefaults.solver,
      kernel_smooth: predictionDefaults.kernel_smooth,
    });
  }, [defaultsReady, predictionDefaults]);

  const median = data ? computeMedian(data) : 0;
  const isPrediction = meta ? !meta.realized_price : false;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Tutorial />
      <div style={{
        borderLeft: "4px solid var(--accent)",
        padding: "22px 24px",
        background: "var(--accent-soft)",
        border: "1px solid var(--accent-border)",
        borderRadius: "0 8px 8px 0",
        maxWidth: "100%",
      }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 30, lineHeight: 1.18, color: "var(--text)", letterSpacing: 0 }}>
          Predict where a stock is headed based on option prices
        </h1>
        <p style={{ margin: 0, fontSize: 17, color: "var(--text-soft)", lineHeight: 1.6, maxWidth: 880 }}>
          Decode the market's implied odds from 90 million+ options data points, then see the upside,
          downside, and timing behind any price target.
          {" "}
          <span
            onClick={() => setShowExplainer(true)}
            style={{ color: "var(--success)", cursor: "pointer", fontWeight: 800, marginLeft: 8 }}
          >
            Explain how it works
          </span>
        </p>
      </div>

      <PredictionForm
        onSubmit={handleSubmit}
        loading={loading}
        events={marketEvents}
        hoveredEventIndex={hoveredEventIndex}
        onEventHover={setHoveredEventIndex}
        onStartTutorial={startTutorial}
        defaults={predictionDefaults}
        timeline={appDefaults?.timeline}
      />

      {loading && <ProgressBar progress={progress} stage={stage} />}

      {error && (
        <div
          style={{
            background: "var(--danger-soft)",
            border: "1px solid var(--danger)",
            borderRadius: 8,
            padding: 14,
            color: "var(--danger)",
            fontSize: 14,
          }}
        >
          {error}
        </div>
      )}

      {data && meta && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 20, alignItems: "stretch" }}>
            <SummaryStats data={data} meta={meta} />
            <MarketContext
              events={marketEvents}
              loading={marketLoading}
              disclaimer={marketDisclaimer}
              hoveredIndex={hoveredEventIndex}
              onHover={setHoveredEventIndex}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 20 }}>
            <PdfChart key={`pdf-${meta.obs_date}-${meta.target_date}-${ciLevel}`} data={data} spot={meta.spot} realized={isPrediction ? undefined : meta.realized_price} predicted={median} ciLevel={ciLevel} onCiLevelChange={setCiLevel} />
            <CdfChart key={`cdf-${meta.obs_date}-${meta.target_date}-${ciLevel}`} data={data} spot={meta.spot} realized={isPrediction ? undefined : meta.realized_price} predicted={median} ciLevel={ciLevel} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 20 }}>
            {ivSmile && (
              <IvSmileChart ivSmile={ivSmile} spot={meta.spot} />
            )}
            {greeks && (
              <GreeksChart greeks={greeks} spot={meta.spot} />
            )}
          </div>

          <HeatMapSection ticker={meta.ticker} />
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
          background: "rgba(0,0,0,0.58)",
          zIndex: 10000,
        }}
      />
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "32px 36px",
          maxWidth: 640,
          width: "90vw",
          maxHeight: "80vh",
          overflowY: "auto",
          zIndex: 10001,
          boxShadow: "var(--shadow)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 22, color: "var(--text)" }}>How It Works</h2>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              fontSize: 22,
              cursor: "pointer",
              padding: "0 4px",
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20, fontSize: 15, color: "var(--text-soft)", lineHeight: 1.7 }}>
          <Section title="The Idea">
            Option prices encode the market's collective expectation of where a stock will be
            on a future date. This tool reverses the Black-Scholes pricing model to extract
            the risk-neutral probability distribution hidden in those prices, turning option
            premiums back into a full forecast of future price outcomes.
          </Section>

          <Section title="The Approach">
            Black-Scholes normally takes volatility in and gives a price out. We reverse it:
            given market prices across many strikes, we solve for the implied volatility at
            each one, producing the IV smile. That curve is smoothed,
            then we reprice options on a dense grid and take the second derivative with respect
            to strike (Breeden-Litzenberger) to recover the risk-neutral probability
            distribution of the stock's future price.
          </Section>

          <Section title="Why It's Useful">
            <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "var(--text)" }}>See the full picture</strong>: not just a
                point estimate, but the entire range of outcomes the market is pricing in.
              </li>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "var(--text)" }}>Quantify tail risk</strong>: understand the
                probability of extreme moves that simple models miss.
              </li>
              <li style={{ marginBottom: 6 }}>
                <strong style={{ color: "var(--text)" }}>Backtest accuracy</strong>: set a past target
                date and compare the predicted distribution against what actually happened.
              </li>
              <li>
                <strong style={{ color: "var(--text)" }}>Market consensus</strong>: this reflects the
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
            background: "var(--success)",
            color: "var(--text-on-accent)",
            cursor: "pointer",
            fontSize: 15,
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
      <h3 style={{ margin: "0 0 6px", fontSize: 16, color: "var(--success)", fontWeight: 800 }}>{title}</h3>
      <div>{children}</div>
    </div>
  );
}
