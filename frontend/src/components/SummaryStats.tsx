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
      color: "#2ecc71",
      bg: "rgba(46, 204, 113, 0.12)",
      explanation: "Realized price landed in the middle 50% of the predicted distribution — the market priced this move correctly.",
    };
  }
  if ((cdfPct >= 0.05 && cdfPct < 0.25) || (cdfPct > 0.75 && cdfPct <= 0.95)) {
    return {
      label: "Tail Event",
      color: "#f1c40f",
      bg: "rgba(241, 196, 15, 0.12)",
      explanation: "Realized price was in the outer range of the distribution — an uncommon but not extreme outcome. The market underestimated how far the price would move.",
    };
  }
  return {
    label: "Outlier",
    color: "#e74c3c",
    bg: "rgba(231, 76, 60, 0.12)",
    explanation: "Realized price fell outside the 90% confidence interval — a rare event the options market did not anticipate. This could indicate a black swan, earnings surprise, or major news.",
  };
}

export default function SummaryStats({ data, meta }: Props) {
  const { prices, pdf, cdf } = data;

  const integral = trapezoid(pdf, prices);
  const meanPrice = trapezoid(
    prices.map((p, i) => p * pdf[i]),
    prices
  );
  const median = interpCdf(0.5, cdf, prices);
  const p5 = interpCdf(0.05, cdf, prices);
  const p25 = interpCdf(0.25, cdf, prices);
  const p75 = interpCdf(0.75, cdf, prices);
  const p95 = interpCdf(0.95, cdf, prices);

  // Distribution shape
  const variance = trapezoid(
    prices.map((p, i) => (p - meanPrice) ** 2 * pdf[i]),
    prices
  );
  const stdDev = Math.sqrt(variance);
  const skew = trapezoid(
    prices.map((p, i) => ((p - meanPrice) / stdDev) ** 3 * pdf[i]),
    prices
  );
  const expectedMove = ((p75 - p25) / 2 / meta.spot * 100);
  const cdfAtSpot = interpCdfAt(meta.spot, prices, cdf);
  const downProb = cdfAtSpot * 100;
  const upProb = (1 - cdfAtSpot) * 100;

  const obsLabel = meta.obs_date_from === meta.obs_date_to
    ? meta.obs_date_from
    : `${meta.obs_date_from} — ${meta.obs_date_to}`;

  const cdfPct = meta.realized_price != null
    ? interpCdfAt(meta.realized_price, prices, cdf)
    : null;
  const badge = cdfPct != null ? getAccuracyBadge(cdfPct) : null;

  const stats: { label: string; value: string; highlight?: string }[] = [
    { label: "Ticker", value: meta.ticker },
    { label: "Observation", value: obsLabel },
    ...(meta.days_averaged > 1 ? [{ label: "Days Averaged", value: `${meta.days_averaged} trading days` }] : []),
    { label: "Target Date", value: meta.target_date },
    { label: "Horizon", value: `${meta.days_forward} days` },
    { label: "Spot (obs date)", value: `$${meta.spot.toFixed(2)}` },
    { label: "E[Price]", value: `$${meanPrice.toFixed(2)}` },
    { label: "Median", value: `$${median.toFixed(2)}` },
    { label: "90% CI", value: `$${p5.toFixed(0)} — $${p95.toFixed(0)}` },
    { label: "Std Dev", value: `$${stdDev.toFixed(2)}` },
    { label: "Skew", value: skew.toFixed(2), highlight: skew < -0.3 ? "#e74c3c" : skew > 0.3 ? "#2ecc71" : undefined },
    { label: "Expected Move", value: `±${expectedMove.toFixed(1)}%` },
    { label: "P(down) / P(up)", value: `${downProb.toFixed(0)}% / ${upProb.toFixed(0)}%` },
    ...(meta.data_source ? [{ label: "Data Source", value: meta.data_source }] : []),
    { label: "Expiry Used", value: meta.expiry_used },
  ];

  if (meta.realized_price != null && cdfPct != null) {
    const error = meta.realized_price - median;
    stats.push(
      { label: "Actual Price", value: `$${meta.realized_price.toFixed(2)}`, highlight: "#2ecc71" },
      { label: "Error (vs median)", value: `${error >= 0 ? "+" : ""}$${error.toFixed(2)}` },
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Stats grid */}
      <div
        style={{
          background: "#1a1a2e",
          borderRadius: 8,
          padding: 16,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
          gap: 12,
        }}
      >
        {stats.map((s) => (
          <div key={s.label}>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 4 }}>
              {s.label}
            </div>
            <div style={{ fontSize: 15, fontWeight: 600, color: s.highlight || "#e0e0e0" }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      {/* Accuracy badge */}
      {badge && cdfPct != null && (
        <div
          style={{
            background: badge.bg,
            border: `1px solid ${badge.color}33`,
            borderRadius: 8,
            padding: "12px 16px",
            display: "flex",
            gap: 12,
            alignItems: "start",
          }}
        >
          <div
            style={{
              background: badge.color,
              color: "#000",
              fontWeight: 700,
              fontSize: 12,
              padding: "3px 10px",
              borderRadius: 4,
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}
          >
            {badge.label}
          </div>
          <div style={{ fontSize: 13, color: "#ccc", lineHeight: 1.5 }}>
            <span style={{ color: badge.color, fontWeight: 600 }}>
              CDF Percentile: {(cdfPct * 100).toFixed(1)}%
            </span>
            {" — "}
            {badge.explanation}
          </div>
        </div>
      )}
    </div>
  );
}
