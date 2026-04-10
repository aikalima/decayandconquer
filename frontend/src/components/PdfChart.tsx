import React from "react";
import {
  Chart as ChartJS,
  LineElement,
  PointElement,
  Filler,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { PredictionData } from "../types/prediction";

ChartJS.register(
  LineElement,
  PointElement,
  Filler,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend
);

interface Props {
  data: PredictionData;
  spot: number;
  realized?: number;
  predicted?: number;
  ciLevel?: 50 | 90;
  onCiLevelChange?: (level: 50 | 90) => void;
}

function findIdx(prices: number[], target: number): number {
  return prices.reduce(
    (best, p, i) => (Math.abs(p - target) < Math.abs(prices[best] - target) ? i : best),
    0
  );
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

export default React.memo(function PdfChart({ data, spot, realized, predicted, ciLevel = 90, onCiLevelChange }: Props) {
  const step = Math.max(1, Math.floor(data.prices.length / 500));
  const prices = data.prices.filter((_, i) => i % step === 0);
  const pdf = data.pdf.filter((_, i) => i % step === 0);
  const cdf = data.cdf.filter((_, i) => i % step === 0);

  const tailPct = (100 - ciLevel) / 2 / 100; // 50% CI -> 0.25, 90% CI -> 0.05
  const pLow = interpCdf(tailPct, data.cdf, data.prices);
  const pHigh = interpCdf(1 - tailPct, data.cdf, data.prices);

  // PDF data split: inside CI gets full color, outside gets lighter
  const pdfInside = pdf.map((v, i) =>
    prices[i] >= pLow && prices[i] <= pHigh ? v : null
  );
  const pdfOutside = pdf.map((v, i) =>
    prices[i] < pLow || prices[i] > pHigh ? v : null
  );

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, minHeight: 300 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h3 style={{ margin: 0, fontSize: 15, color: "#ccc" }}>
          Predicted Range
        </h3>
        {onCiLevelChange && (
          <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
            <span style={{ fontSize: 10, color: "#666", marginRight: 2 }}>Chance price lands in shaded range:</span>
            {([{ level: 50 as const, label: "Coin flip (50%)" }, { level: 90 as const, label: "Near certain (90%)" }]).map(({ level, label }) => (
              <button
                key={level}
                onClick={() => onCiLevelChange(level)}
                style={{
                  padding: "3px 8px",
                  borderRadius: 4,
                  border: `1px solid ${ciLevel === level ? "#6c63ff" : "#333"}`,
                  background: ciLevel === level ? "#6c63ff" : "transparent",
                  color: ciLevel === level ? "#fff" : "#888",
                  cursor: "pointer",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <p style={{ margin: "0 0 12px", fontSize: 11, color: "#666" }}>
        The market-implied range of likely prices. The peak is the most probable outcome;
        the shaded area covers the confidence interval.
      </p>
      <Line
        data={{
          labels: prices.map((p) => p.toFixed(1)),
          datasets: [
            {
              label: "90% CI",
              data: pdfInside,
              borderColor: "transparent",
              backgroundColor: "rgba(168, 130, 255, 0.22)",
              fill: true,
              pointRadius: 0,
              borderWidth: 0,
              spanGaps: false,
            },
            {
              label: "Tails",
              data: pdfOutside,
              borderColor: "transparent",
              backgroundColor: "rgba(168, 130, 255, 0.06)",
              fill: true,
              pointRadius: 0,
              borderWidth: 0,
              spanGaps: false,
            },
            {
              label: "PDF",
              data: pdf,
              borderColor: "#4a90d9",
              backgroundColor: "transparent",
              fill: false,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
            },
          ],
        }}
        options={{
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              filter: (item) => item.datasetIndex === 2, // only PDF line
              callbacks: {
                title: (items) => `Price: $${items[0].label}`,
                label: (item) =>
                  `Density: ${Number(item.raw).toExponential(3)}`,
              },
            },
          },
          scales: {
            x: {
              type: "category",
              title: { display: true, text: "Predicted Price ($)", color: "#888" },
              ticks: { color: "#666", maxTicksLimit: 10 },
              grid: { color: "#222" },
            },
            y: {
              title: { display: true, text: "Likelihood", color: "#888" },
              ticks: { color: "#666" },
              grid: { color: "#222" },
            },
          },
          animation: {
            onComplete: ({ chart }) => {
              const ctx = chart.ctx;
              const xScale = chart.scales.x;
              const yTop = chart.chartArea.top;
              const yBottom = chart.chartArea.bottom;

              ctx.save();

              // 90% CI boundary lines (subtle)
              for (const bound of [pLow, pHigh]) {
                const bx = xScale.getPixelForValue(findIdx(prices, bound));
                ctx.strokeStyle = "rgba(168, 130, 255, 0.35)";
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(bx, yTop);
                ctx.lineTo(bx, yBottom);
                ctx.stroke();
              }
              // CI label
              const pLowX = xScale.getPixelForValue(findIdx(prices, pLow));
              ctx.fillStyle = "rgba(168, 130, 255, 0.7)";
              ctx.font = "10px sans-serif";
              ctx.setLineDash([]);
              ctx.fillText(`${ciLevel}% CI: $${pLow.toFixed(0)}–$${pHigh.toFixed(0)}`, pLowX + 4, yBottom - 6);

              // Spot price line (red dashed)
              const spotX = xScale.getPixelForValue(findIdx(prices, spot));
              ctx.strokeStyle = "#e74c3c";
              ctx.lineWidth = 1.5;
              ctx.setLineDash([6, 4]);
              ctx.beginPath();
              ctx.moveTo(spotX, yTop);
              ctx.lineTo(spotX, yBottom);
              ctx.stroke();
              ctx.fillStyle = "#e74c3c";
              ctx.font = "11px sans-serif";
              ctx.fillText(`Spot $${spot.toFixed(0)}`, spotX + 4, yTop + 14);

              // Predicted median line (green dashed)
              if (predicted != null) {
                const predX = xScale.getPixelForValue(findIdx(prices, predicted));
                ctx.strokeStyle = "#2ecc71";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(predX, yTop);
                ctx.lineTo(predX, yBottom);
                ctx.stroke();
                ctx.fillStyle = "#2ecc71";
                ctx.setLineDash([]);
                ctx.fillText(`Predicted $${predicted.toFixed(0)}`, predX + 4, yTop + 42);
              }

              // Realized price line (cyan solid)
              if (realized != null) {
                const realX = xScale.getPixelForValue(findIdx(prices, realized));
                ctx.strokeStyle = "#00d2ff";
                ctx.lineWidth = 2;
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(realX, yTop);
                ctx.lineTo(realX, yBottom);
                ctx.stroke();
                ctx.fillStyle = "#00d2ff";
                ctx.fillText(`Actual $${realized.toFixed(0)}`, realX + 4, yTop + 28);
              }

              ctx.restore();
            },
          },
        }}
      />
    </div>
  );
});
