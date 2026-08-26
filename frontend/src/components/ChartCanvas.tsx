import type { ToolResult } from "../api/client";
import PdfChart from "./PdfChart";
import CdfChart from "./CdfChart";
import RiskGauge from "./RiskGauge";
import type { PredictionData, IvSmile } from "../types/prediction";
import { useState } from "react";

interface PredictionChartData {
  ticker: string;
  label: string;
  data: PredictionData;
  spot: number;
  predicted: number;
  realized?: number;
  ivSmile?: IvSmile;
}

interface Props {
  toolResults: ToolResult[];
}

function extractChartData(result: ToolResult): PredictionChartData | null {
  if (result.tool !== "run_prediction") return null;
  const o = result.output as Record<string, unknown>;
  if (o.error || !o.has_chart_data) return null;

  // We don't have the full PDF/CDF arrays from the chat tool, just summary stats.
  // Generate a simple Gaussian approximation for visualization.
  const median = Number(o.median);
  const stdDev = Number(o.std_dev);
  const n = 500;
  const lo = median - 4 * stdDev;
  const hi = median + 4 * stdDev;
  const step = (hi - lo) / (n - 1);

  const prices: number[] = [];
  const pdf: number[] = [];
  const cdf: number[] = [];

  // Use a skewed normal approximation based on P5/P95 asymmetry
  const p5 = Number(o.p5);
  const p95 = Number(o.p95);
  const leftWidth = median - p5;
  const rightWidth = p95 - median;

  for (let i = 0; i < n; i++) {
    const price = lo + i * step;
    prices.push(price);
    // Use different widths for left/right to capture skew
    const sigma = price < median ? leftWidth / 1.645 : rightWidth / 1.645;
    const z = (price - median) / sigma;
    pdf.push(Math.exp(-0.5 * z * z) / (sigma * Math.sqrt(2 * Math.PI)));
  }

  // Normalise PDF
  let area = 0;
  for (let i = 1; i < n; i++) {
    area += ((pdf[i] + pdf[i - 1]) / 2) * (prices[i] - prices[i - 1]);
  }
  for (let i = 0; i < n; i++) pdf[i] /= area;

  // CDF
  let cumul = 0;
  for (let i = 0; i < n; i++) {
    if (i > 0) cumul += ((pdf[i] + pdf[i - 1]) / 2) * (prices[i] - prices[i - 1]);
    cdf.push(Math.min(1, cumul));
  }

  const obsLabel = o.obs_date_from !== o.obs_date_to
    ? `${o.obs_date_from} to ${o.obs_date_to}`
    : String(o.obs_date_from);

  return {
    ticker: String(o.ticker),
    label: `${o.ticker} (${obsLabel} → ${o.target_date})`,
    data: { prices, pdf, cdf },
    spot: Number(o.spot),
    predicted: median,
    realized: o.realized_price != null ? Number(o.realized_price) : undefined,
  };
}

export default function ChartCanvas({ toolResults }: Props) {
  const [ciLevel, setCiLevel] = useState<50 | 90>(90);

  // Collect all prediction results for charting
  const charts: PredictionChartData[] = [];
  for (const tr of toolResults) {
    const chart = extractChartData(tr);
    if (chart) charts.push(chart);
  }

  if (charts.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: "var(--muted)",
          fontSize: 14,
        }}
      >
        <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
        <p>Charts will appear here when you ask about stocks.</p>
        <p style={{ fontSize: 12, color: "var(--muted-2)" }}>
          Try: "What's SPY's prediction for the next monthly expiry based on recent options data?"
        </p>
      </div>
    );
  }

  // Show the most recent prediction (last in array)
  const latest = charts[charts.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, overflow: "auto", padding: "0 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: 16, color: "var(--text)" }}>{latest.label}</h3>
        <div style={{ display: "flex", gap: 6 }}>
          {([50, 90] as const).map((level) => (
            <button
              key={level}
              onClick={() => setCiLevel(level)}
              style={{
                padding: "3px 10px",
                borderRadius: 4,
                border: `1px solid ${ciLevel === level ? "var(--accent)" : "var(--border)"}`,
                background: ciLevel === level ? "var(--accent)" : "transparent",
                color: ciLevel === level ? "var(--text-on-accent)" : "var(--muted)",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {level}% CI
            </button>
          ))}
        </div>
      </div>

      <RiskGauge
        data={latest.data}
        spot={latest.spot}
        predicted={latest.predicted}
        realized={latest.realized}
      />

      <PdfChart
        key={`pdf-${latest.ticker}-${ciLevel}`}
        data={latest.data}
        spot={latest.spot}
        realized={latest.realized}
        predicted={latest.predicted}
        ciLevel={ciLevel}
      />

      <CdfChart
        key={`cdf-${latest.ticker}-${ciLevel}`}
        data={latest.data}
        spot={latest.spot}
        realized={latest.realized}
        predicted={latest.predicted}
        ciLevel={ciLevel}
      />

      {/* If comparing multiple tickers, show a mini summary grid */}
      {charts.length > 1 && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 14 }}>
          <h4 style={{ margin: "0 0 8px", fontSize: 14, color: "var(--muted)" }}>All Predictions</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
            {charts.map((c, i) => (
              <div
                key={i}
                style={{
                  padding: 8,
                  borderRadius: 6,
                  background: c === latest ? "var(--surface-hover)" : "var(--surface-subtle)",
                  border: `1px solid ${c === latest ? "var(--accent)" : "var(--border)"}`,
                  fontSize: 12,
                }}
              >
                <div style={{ fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>{c.ticker}</div>
                <div style={{ color: "var(--muted)" }}>
                  Median: ${c.predicted.toFixed(0)}
                  {c.realized != null && (
                    <span style={{ color: "var(--success)" }}> | Actual: ${c.realized.toFixed(0)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
