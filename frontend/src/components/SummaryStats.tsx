import type { PredictionData, PredictionMeta } from "../types/prediction";

interface Props {
  data: PredictionData;
  meta: PredictionMeta;
}

function trapezoid(y: number[], x: number[]): number {
  let sum = 0;
  for (let i = 1; i < x.length; i++) {
    sum += ((y[i] + y[i - 1]) / 2) * (x[i] - x[i - 1]);
  }
  return sum;
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

export function interpCdfAt(price: number, prices: number[], cdf: number[]): number {
  if (price <= prices[0]) return 0;
  if (price >= prices[prices.length - 1]) return 1;
  for (let i = 1; i < prices.length; i++) {
    if (prices[i] >= price) {
      const t = (price - prices[i - 1]) / (prices[i] - prices[i - 1]);
      return cdf[i - 1] + t * (cdf[i] - cdf[i - 1]);
    }
  }
  return 1;
}

export function getAccuracyBadge(cdfPct: number): { label: string; color: string; bg: string; explanation: string } {
  if (cdfPct >= 0.25 && cdfPct <= 0.75) {
    return {
      label: "Accurate",
      color: "#2ecc71",
      bg: "rgba(46, 204, 113, 0.12)",
      explanation: "Realized price landed in the middle 50% of the predicted distribution. The market priced this move correctly.",
    };
  }
  if ((cdfPct >= 0.05 && cdfPct < 0.25) || (cdfPct > 0.75 && cdfPct <= 0.95)) {
    return {
      label: "Tail Event",
      color: "#f1c40f",
      bg: "rgba(241, 196, 15, 0.12)",
      explanation: "Realized price was in the outer range of the distribution. An uncommon but not extreme outcome.",
    };
  }
  return {
    label: "Outlier",
    color: "#e74c3c",
    bg: "rgba(231, 76, 60, 0.12)",
    explanation: "Realized price fell outside the 90% confidence interval. A rare event the options market did not anticipate.",
  };
}

export default function SummaryStats({ data, meta }: Props) {
  const { prices, pdf, cdf } = data;

  const meanPrice = trapezoid(
    prices.map((p, i) => p * pdf[i]),
    prices
  );
  const median = interpCdf(0.5, cdf, prices);
  const p5 = interpCdf(0.05, cdf, prices);
  const p95 = interpCdf(0.95, cdf, prices);
  const variance = trapezoid(
    prices.map((p, i) => (p - meanPrice) ** 2 * pdf[i]),
    prices
  );
  const stdDev = Math.sqrt(variance);
  const skew = trapezoid(
    prices.map((p, i) => ((p - meanPrice) / stdDev) ** 3 * pdf[i]),
    prices
  );
  const cdfAtSpot = interpCdfAt(meta.spot, prices, cdf);
  const downProb = cdfAtSpot * 100;
  const upProb = (1 - cdfAtSpot) * 100;

  const hasRealized = meta.realized_price != null;
  const cdfPct = hasRealized ? interpCdfAt(meta.realized_price!, prices, cdf) : null;
  const badge = cdfPct != null ? getAccuracyBadge(cdfPct) : null;
  const isPrediction = !hasRealized;

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Top banner: Result summary */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 12,
        padding: "10px 14px",
        borderRadius: 8,
        background: hasRealized ? "#0f1f0f" : "#0f1f1f",
        border: `1px solid ${hasRealized ? "#2a5a2a" : "#2a5a5a"}`,
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <strong style={{ color: isPrediction ? "#2ecc71" : "#2ecc71", fontSize: 15 }}>
              {meta.ticker} {isPrediction ? "Prediction" : "Backtest"}
            </strong>
            {badge && (
              <span style={{
                background: badge.color,
                color: "#000",
                fontWeight: 700,
                fontSize: 10,
                padding: "2px 8px",
                borderRadius: 4,
              }}>
                {badge.label}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "#aaa", lineHeight: 1.6 }}>
            {isPrediction ? (
              <>
                Given option prices from {meta.obs_date_from} to {meta.obs_date_to}, the
                market predicts {meta.ticker} around <strong style={{ color: "#ccc" }}>${median.toFixed(0)}</strong> by {meta.target_date}.
                {" "}The current price is <strong style={{ color: "#ccc" }}>${meta.spot.toFixed(2)}</strong>.
              </>
            ) : (
              <>
                Predicted <strong style={{ color: "#ccc" }}>${median.toFixed(0)}</strong>,
                actual was <strong style={{ color: "#2ecc71" }}>${meta.realized_price!.toFixed(2)}</strong>.
                {badge && (
                  <span style={{ color: "#888" }}> {badge.explanation}</span>
                )}
                {cdfPct != null && (
                  <span style={{ color: "#888" }}>
                    {" "}Only <strong style={{ color: badge?.color || "#ccc" }}>{(cdfPct * 100).toFixed(1)}%</strong> of predicted outcomes were below the actual price.
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Grouped stats */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <StatsGroup title="Setup" color="#6c63ff">
          <Stat label="Observation Window" value={`${meta.obs_date_from} to ${meta.obs_date_to}`} tooltip="The date range of options data used to build the prediction." />
          {meta.days_averaged > 1 && (
            <Stat label="Trading Days" value={`${meta.days_averaged}`} tooltip="Number of trading days used to average implied volatility." />
          )}
          <Stat label="Expiry Used" value={meta.expiry_used} tooltip="Options expiry date used (nearest to target)." />
        </StatsGroup>

        <StatsGroup title="Prediction" color="#2ecc71" columns={2}>
          <Stat label="Target Date" value={meta.target_date} tooltip="The date for which the price distribution is predicted." />
          <Stat label="Horizon" value={`${meta.days_forward} days`} tooltip="Calendar days between observation end and target date." />
          <Stat label="Spot" value={`$${meta.spot.toFixed(2)}`} tooltip="Stock price at observation date." />
          <Stat label="Prediction" value={`$${median.toFixed(2)}`} tooltip="Predicted price (50th percentile of the distribution)." />
          <Stat label="90% CI" value={`$${p5.toFixed(0)} - $${p95.toFixed(0)}`} tooltip="90% confidence interval (5th to 95th percentile)." />
          {hasRealized && (
            <>
              <Stat label="Actual Price" value={`$${meta.realized_price!.toFixed(2)}`} highlight="#2ecc71" tooltip="Actual closing price on the target date." />
              <Stat label="Error" value={`${(meta.realized_price! - median) >= 0 ? "+" : ""}$${(meta.realized_price! - median).toFixed(2)}`} tooltip="Actual price minus predicted median." />
            </>
          )}
        </StatsGroup>

        <StatsGroup title="Risk Profile" color="#e67e22">
          <Stat label="Std Dev" value={`$${stdDev.toFixed(2)}`} tooltip="Standard deviation. Higher = more uncertainty." />
          <Stat label="Skew" value={skew.toFixed(2)} highlight={skew < -0.3 ? "#e74c3c" : skew > 0.3 ? "#2ecc71" : undefined} tooltip="Distribution asymmetry. Negative = crash risk priced in." />
          <Stat label="P(down) / P(up)" value={`${downProb.toFixed(0)}% / ${upProb.toFixed(0)}%`} tooltip="Probability of price below/above current spot at target date." />
        </StatsGroup>
      </div>
    </div>
  );
}

function StatsGroup({ title, children, columns, color }: { title: string; children: React.ReactNode; columns?: number; color?: string }) {
  return (
    <div style={{
      background: color ? `${color}08` : "#0f0f1a",
      border: `1px solid ${color ? `${color}30` : "#1a1a2e"}`,
      borderRadius: 8,
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: color || "#555", textTransform: "uppercase", letterSpacing: 1 }}>
        {title}
      </div>
      {columns ? (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: 8 }}>
          {children}
        </div>
      ) : children}
    </div>
  );
}

function Stat({ label, value, highlight, tooltip }: {
  label: string;
  value: string;
  highlight?: string;
  tooltip: string;
}) {
  return (
    <div title={tooltip} style={{ cursor: "help" }}>
      <div style={{ fontSize: 10, color: "#666", marginBottom: 2, borderBottom: "1px dotted #333", display: "inline" }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: highlight || "#e0e0e0" }}>
        {value}
      </div>
    </div>
  );
}
