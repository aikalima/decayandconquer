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
      explanation: "Realized price was in the outer range of the distribution. An uncommon but not extreme outcome. The market underestimated how far the price would move.",
    };
  }
  return {
    label: "Outlier",
    color: "#e74c3c",
    bg: "rgba(231, 76, 60, 0.12)",
    explanation: "Realized price fell outside the 90% confidence interval. A rare event the options market did not anticipate. Could indicate a black swan, earnings surprise, or major news.",
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

  const cdfPct = meta.realized_price != null
    ? interpCdfAt(meta.realized_price, prices, cdf)
    : null;
  const badge = cdfPct != null ? getAccuracyBadge(cdfPct) : null;

  const stats: { label: string; value: string; highlight?: string; tooltip: string }[] = [
    { label: "Ticker", value: meta.ticker, tooltip: "The stock symbol being analyzed." },
    { label: "Observation Start", value: meta.obs_date_from, tooltip: "Start of the observation window when the options market was observed." },
    { label: "Observation End", value: meta.obs_date_to, tooltip: "End of the observation window. If different from start, IV is averaged across all trading days in the range." },
    ...(meta.days_averaged > 1 ? [{ label: "Days Averaged", value: `${meta.days_averaged} trading days`, tooltip: "Number of trading days used to average implied volatility. More days = smoother, more stable prediction." }] : []),
    { label: "Target Date", value: meta.target_date, tooltip: "The date for which the price distribution is predicted. Options expiring near this date are used." },
    { label: "Horizon", value: `${meta.days_forward} days`, tooltip: "Number of calendar days between the observation end date and the target date." },
    { label: "Spot (obs date)", value: `$${meta.spot.toFixed(2)}`, tooltip: "The stock's closing price on the observation date. This is the starting point for the prediction." },
    { label: "E[Price]", value: `$${meanPrice.toFixed(2)}`, tooltip: "Expected value (mean) of the predicted price distribution. Weighted average of all possible prices by their probability." },
    { label: "Median", value: `$${median.toFixed(2)}`, tooltip: "The 50th percentile. There's a 50% chance the price ends up above this and 50% below." },
    { label: "90% CI", value: `$${p5.toFixed(0)} to $${p95.toFixed(0)}`, tooltip: "90% Confidence Interval. The market implies a 90% probability that the price falls within this range (5th to 95th percentile)." },
    { label: "Std Dev", value: `$${stdDev.toFixed(2)}`, tooltip: "Standard deviation of the predicted distribution. Higher = more uncertainty about the future price." },
    { label: "Skew", value: skew.toFixed(2), highlight: skew < -0.3 ? "#e74c3c" : skew > 0.3 ? "#2ecc71" : undefined, tooltip: "Distribution asymmetry. Negative (red) = heavier left tail, meaning crash risk is priced in. Positive (green) = upside bias. Near zero = symmetric." },
    { label: "Expected Move", value: `±${expectedMove.toFixed(1)}%`, tooltip: "The interquartile range (P25 to P75) expressed as a percentage of the spot price. Represents the market's 'typical' expected move." },
    { label: "P(down) / P(up)", value: `${downProb.toFixed(0)}% / ${upProb.toFixed(0)}%`, tooltip: "Probability of the price being below (down) or above (up) the current spot price at the target date." },
    { label: "Expiry Used", value: meta.expiry_used, tooltip: "The actual options expiry date used (nearest standard monthly expiry to the target date)." },
  ];

  if (meta.realized_price != null && cdfPct != null) {
    const error = meta.realized_price - median;
    stats.push(
      { label: "Actual Price", value: `$${meta.realized_price.toFixed(2)}`, highlight: "#2ecc71", tooltip: "The stock's actual closing price on the target date, fetched for backtesting comparison." },
      { label: "Error (vs median)", value: `${error >= 0 ? "+" : ""}$${error.toFixed(2)}`, tooltip: "Prediction error: actual price minus predicted median. Positive = price was higher than predicted." },
    );
  }

  return (
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
        <div key={s.label} title={s.tooltip} style={{ cursor: "help" }}>
          <div style={{ fontSize: 11, color: "#888", marginBottom: 4, borderBottom: "1px dotted #444", display: "inline" }}>
            {s.label}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: s.highlight || "#e0e0e0" }}>
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}
