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

export default function SummaryStats({ data, meta }: Props) {
  const { prices, pdf, cdf } = data;

  const integral = trapezoid(pdf, prices);
  const meanPrice = trapezoid(
    prices.map((p, i) => p * pdf[i]),
    prices
  );
  const median = interpCdf(0.5, cdf, prices);
  const p5 = interpCdf(0.05, cdf, prices);
  const p95 = interpCdf(0.95, cdf, prices);

  const obsLabel = meta.obs_date_from === meta.obs_date_to
    ? meta.obs_date_from
    : `${meta.obs_date_from} — ${meta.obs_date_to}`;

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
    { label: "Integral PDF", value: integral.toFixed(4) },
  ];

  if (meta.realized_price != null) {
    const cdfPct = interpCdfAt(meta.realized_price, prices, cdf);
    const error = meta.realized_price - median;
    stats.push(
      { label: "Actual Price", value: `$${meta.realized_price.toFixed(2)}`, highlight: "#2ecc71" },
      { label: "CDF Percentile", value: `${(cdfPct * 100).toFixed(1)}%` },
      { label: "Error (vs median)", value: `${error >= 0 ? "+" : ""}$${error.toFixed(2)}` },
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
  );
}
