import type { PredictionData } from "../types/prediction";

interface Props {
  data: PredictionData;
  spot: number;
  predicted: number;
  realized?: number;
}

function interpCdf(target: number, cdf: number[], prices: number[]): number {
  for (let i = 1; i < cdf.length; i++) {
    if (cdf[i] >= target) {
      const t = (target - cdf[i - 1]) / (cdf[i] - cdf[i - 1]);
      return prices[i - 1] + t * (prices[i] - prices[i - 1]);
    }
  }
  return prices[prices.length - 1];
}

export default function RiskGauge({ data, spot, predicted, realized }: Props) {
  const { prices, cdf } = data;
  const min = prices[0];
  const max = prices[prices.length - 1];
  const range = max - min;

  const p5 = interpCdf(0.05, cdf, prices);
  const p25 = interpCdf(0.25, cdf, prices);
  const p75 = interpCdf(0.75, cdf, prices);
  const p95 = interpCdf(0.95, cdf, prices);

  const pct = (v: number) => ((v - min) / range) * 100;

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "16px 18px", boxShadow: "var(--shadow-soft)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 750 }}>Price Distribution Range</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          ${min.toFixed(0)} to ${max.toFixed(0)}
        </span>
      </div>

      <div
        style={{
          position: "relative",
          height: 32,
          borderRadius: 4,
          overflow: "hidden",
          background: "var(--input-bg)",
        }}
      >
        {/* Tail zones */}
        <Zone left={0} width={pct(p5)} color="var(--risk-tint)" />
        <Zone left={pct(p95)} width={100 - pct(p95)} color="var(--risk-tint)" />

        {/* 90% CI zones */}
        <Zone left={pct(p5)} width={pct(p25) - pct(p5)} color="var(--brand-tint)" />
        <Zone left={pct(p75)} width={pct(p95) - pct(p75)} color="var(--brand-tint)" />

        {/* 50% CI (core) */}
        <Zone left={pct(p25)} width={pct(p75) - pct(p25)} color="var(--brand-tint)" />

        {/* Markers */}
        <Marker position={pct(spot)} color="var(--risk)" label="Spot" />
        <Marker position={pct(predicted)} color="var(--brand)" label="Pred" />
        {realized != null && (
          <Marker position={pct(realized)} color={realized >= predicted ? "var(--up)" : "var(--down)"} label="Actual" />
        )}
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 6,
          fontSize: 11,
          color: "var(--muted)",
        }}
      >
        <span style={{ color: "var(--risk-text)" }}>P5: ${p5.toFixed(0)}</span>
        <span style={{ color: "var(--brand-text)" }}>P25: ${p25.toFixed(0)}</span>
        <span style={{ color: "var(--text-soft)" }}>Median: ${predicted.toFixed(0)}</span>
        <span style={{ color: "var(--brand-text)" }}>P75: ${p75.toFixed(0)}</span>
        <span style={{ color: "var(--risk-text)" }}>P95: ${p95.toFixed(0)}</span>
      </div>
    </div>
  );
}

function Zone({ left, width, color }: { left: number; width: number; color: string }) {
  return (
    <div
      style={{
        position: "absolute",
        left: `${left}%`,
        width: `${width}%`,
        height: "100%",
        background: color,
      }}
    />
  );
}

function Marker({ position, color, label }: { position: number; color: string; label: string }) {
  const clamped = Math.max(1, Math.min(99, position));
  return (
    <div
      style={{
        position: "absolute",
        left: `${clamped}%`,
        top: 0,
        bottom: 0,
        width: 2,
        background: color,
        zIndex: 2,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: -14,
          left: "50%",
          transform: "translateX(-50%)",
          fontSize: 10,
          color,
          fontWeight: 600,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </div>
    </div>
  );
}
