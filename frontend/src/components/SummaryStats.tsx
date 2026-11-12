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

function interpCdfAt(price: number, prices: number[], cdf: number[]): number {
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

function getAccuracyBadge(cdfPct: number): { label: string; color: string; bg: string; explanation: string } {
  if (cdfPct >= 0.25 && cdfPct <= 0.75) {
    return {
      label: "Accurate",
      color: "var(--brand-text)",
      bg: "var(--brand-tint)",
      explanation: "Realized price landed in the middle 50% of the predicted distribution. The market priced this move correctly.",
    };
  }
  if ((cdfPct >= 0.05 && cdfPct < 0.25) || (cdfPct > 0.75 && cdfPct <= 0.95)) {
    return {
      label: "Tail Event",
      color: "var(--risk-text)",
      bg: "var(--risk-tint)",
      explanation: "Realized price was in the outer range of the distribution. An uncommon but not extreme outcome.",
    };
  }
  return {
    label: "Outlier",
    color: "var(--risk-text)",
    bg: "var(--risk-tint)",
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
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, display: "flex", flexDirection: "column", gap: 16, boxShadow: "var(--shadow-soft)" }}>

      {/* Top banner: Result summary */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 12,
        padding: "12px 14px",
        borderRadius: 8,
        background: "var(--brand-tint)",
        border: "1px solid var(--brand-border)",
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <strong style={{ color: "var(--brand-text)", fontSize: 16 }}>
              {meta.ticker} {isPrediction ? "Prediction" : "Backtest"}
            </strong>
            {badge && (
              <span style={{
                background: badge.bg,
                color: badge.color,
                border: "1px solid currentColor",
                fontWeight: 700,
                fontSize: 11,
                padding: "3px 8px",
                borderRadius: 4,
              }}>
                {badge.label}
              </span>
            )}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-soft)", lineHeight: 1.65 }}>
            {isPrediction ? (
              <>
                Given option prices from {meta.obs_date_from} to {meta.obs_date_to}, the
                market predicts {meta.ticker} around <strong style={{ color: "var(--brand-text)" }}>${median.toFixed(0)}</strong> by {meta.target_date}.
                {" "}The current price is <strong style={{ color: "var(--text)" }}>${meta.spot.toFixed(2)}</strong>.
              </>
            ) : (
              <>
                Predicted <strong style={{ color: "var(--brand-text)" }}>${median.toFixed(0)}</strong>,
                actual was <strong style={{ color: meta.realized_price! >= median ? "var(--up)" : "var(--down)" }}>${meta.realized_price!.toFixed(2)}</strong>.
                {badge && (
                  <span style={{ color: "var(--muted)" }}> {badge.explanation}</span>
                )}
                {cdfPct != null && (
                  <span style={{ color: "var(--muted)" }}>
                    {" "}Only <strong style={{ color: badge?.color || "var(--text)" }}>{(cdfPct * 100).toFixed(1)}%</strong> of predicted outcomes were below the actual price.
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Grouped stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
        <StatsGroup title="Setup" variant="neutral">
          <Stat label="Observation Window" value={`${meta.obs_date_from} to ${meta.obs_date_to}`} tooltip="The date range of options data used to build the prediction." />
          {meta.days_averaged > 1 && (
            <Stat label="Trading Days" value={`${meta.days_averaged}`} tooltip="Number of trading days used to average implied volatility." />
          )}
          <Stat label="Expiry Used" value={meta.expiry_used} tooltip="Options expiry date used (nearest to target)." />
        </StatsGroup>

        <StatsGroup title="Prediction" variant="brand" columns={2}>
          <Stat label="Target Date" value={meta.target_date} tooltip="The date for which the price distribution is predicted." />
          <Stat label="Horizon" value={`${meta.days_forward} days`} tooltip="Calendar days between observation end and target date." />
          <Stat label="Spot" value={`$${meta.spot.toFixed(2)}`} tooltip="Stock price at observation date." />
          <Stat label="Prediction" value={`$${median.toFixed(2)}`} tooltip="Predicted price (50th percentile of the distribution)." />
          <Stat label="90% CI" value={`$${p5.toFixed(0)} - $${p95.toFixed(0)}`} tooltip="90% confidence interval (5th to 95th percentile)." />
          {hasRealized && (
            <>
              <Stat label="Actual Price" value={`$${meta.realized_price!.toFixed(2)}`} highlight={meta.realized_price! >= median ? "var(--up)" : "var(--down)"} tooltip="Actual closing price on the target date." />
              <Stat label="Error" value={`${(meta.realized_price! - median) >= 0 ? "+" : ""}$${(meta.realized_price! - median).toFixed(2)}`} highlight={(meta.realized_price! - median) >= 0 ? "var(--up)" : "var(--down)"} tooltip="Actual price minus predicted median." />
            </>
          )}
        </StatsGroup>

        <StatsGroup title="Risk Profile" variant="risk">
          <Stat label="Std Dev" value={`$${stdDev.toFixed(2)}`} tooltip="Standard deviation. Higher = more uncertainty." />
          <Stat label="Skew" value={skew.toFixed(2)} highlight={skew < -0.3 ? "var(--down)" : skew > 0.3 ? "var(--up)" : undefined} tooltip="Distribution asymmetry. Negative = downside risk priced in." />
          <Stat
            label="P(down) / P(up)"
            value={(
              <>
                <span style={{ color: "var(--down-text)", background: "var(--down-tint)", borderRadius: 4 }}>{downProb.toFixed(0)}%</span>
                {" / "}
                <span style={{ color: "var(--up-text)", background: "var(--up-tint)", borderRadius: 4 }}>{upProb.toFixed(0)}%</span>
              </>
            )}
            tooltip="Probability of price below/above current spot at target date."
          />
        </StatsGroup>
      </div>
    </div>
  );
}

function StatsGroup({ title, children, columns, variant }: { title: string; children: React.ReactNode; columns?: number; variant: "neutral" | "brand" | "risk" }) {
  const styles = {
    neutral: {
      background: "var(--card-bg)",
      border: "var(--border)",
      color: "var(--text)",
    },
    brand: {
      background: "var(--brand-tint)",
      border: "var(--brand-border)",
      color: "var(--brand-text)",
    },
    risk: {
      background: "var(--risk-tint)",
      border: "var(--risk)",
      color: "var(--risk-text)",
    },
  }[variant];

  return (
    <div style={{
      background: styles.background,
      border: `1px solid ${styles.border}`,
      borderRadius: 8,
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: 10,
      color: styles.color,
    }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: styles.color, textTransform: "uppercase", letterSpacing: 0.7 }}>
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
  value: React.ReactNode;
  highlight?: string;
  tooltip: string;
}) {
  return (
    <div title={tooltip} style={{ cursor: "help" }}>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 3, borderBottom: "1px dotted var(--border-strong)", display: "inline" }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 750, color: highlight || "inherit" }}>
        {value}
      </div>
    </div>
  );
}
