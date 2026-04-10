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

export default React.memo(function CdfChart({ data, spot, realized, predicted, ciLevel = 90 }: Props) {
  const step = Math.max(1, Math.floor(data.prices.length / 500));
  const prices = data.prices.filter((_, i) => i % step === 0);
  const cdf = data.cdf.filter((_, i) => i % step === 0);

  const tailPct = (100 - ciLevel) / 2 / 100;
  const pLow = interpCdf(tailPct, data.cdf, data.prices);
  const pHigh = interpCdf(1 - tailPct, data.cdf, data.prices);

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, minHeight: 300 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 15, color: "#ccc" }}>
        Price Probability
      </h3>
      <p style={{ margin: "0 0 12px", fontSize: 11, color: "#666" }}>
        The probability of the price ending up below each level. Read off any price on the
        x-axis to see the chance it stays under that value.
      </p>
      <Line
        data={{
          labels: prices.map((p) => p.toFixed(1)),
          datasets: [
            {
              label: "CDF",
              data: cdf,
              borderColor: "#e67e22",
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
              callbacks: {
                title: (items) => `Price: $${items[0].label}`,
                label: (item) =>
                  `P(Price < x) = ${(Number(item.raw) * 100).toFixed(1)}%`,
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
              min: 0,
              max: 1,
              title: { display: true, text: "P(Price < x)", color: "#888" },
              ticks: {
                color: "#666",
                callback: (v) => `${(Number(v) * 100).toFixed(0)}%`,
              },
              grid: { color: "#222" },
            },
          },
          animation: {
            onComplete: ({ chart }) => {
              const ctx = chart.ctx;
              const xScale = chart.scales.x;
              const yScale = chart.scales.y;
              const yTop = chart.chartArea.top;
              const yBottom = chart.chartArea.bottom;
              const xLeft = chart.chartArea.left;

              ctx.save();

              // CI shaded band
              const pLowX = xScale.getPixelForValue(findIdx(prices, pLow));
              const pHighX = xScale.getPixelForValue(findIdx(prices, pHigh));
              const yLow = yScale.getPixelForValue(tailPct);
              const yHigh = yScale.getPixelForValue(1 - tailPct);
              ctx.fillStyle = "rgba(168, 130, 255, 0.1)";
              ctx.fillRect(pLowX, yTop, pHighX - pLowX, yBottom - yTop);

              // Horizontal lines at CI bounds
              ctx.strokeStyle = "rgba(168, 130, 255, 0.35)";
              ctx.lineWidth = 1;
              ctx.setLineDash([3, 3]);
              ctx.beginPath();
              ctx.moveTo(xLeft, yLow);
              ctx.lineTo(pLowX, yLow);
              ctx.stroke();
              ctx.beginPath();
              ctx.moveTo(xLeft, yHigh);
              ctx.lineTo(pHighX, yHigh);
              ctx.stroke();

              // Vertical CI boundary lines
              ctx.beginPath();
              ctx.moveTo(pLowX, yTop);
              ctx.lineTo(pLowX, yBottom);
              ctx.stroke();
              ctx.beginPath();
              ctx.moveTo(pHighX, yTop);
              ctx.lineTo(pHighX, yBottom);
              ctx.stroke();

              // CI label
              ctx.fillStyle = "rgba(168, 130, 255, 0.7)";
              ctx.font = "10px sans-serif";
              ctx.setLineDash([]);
              ctx.fillText(`${ciLevel}% CI: $${pLow.toFixed(0)}–$${pHigh.toFixed(0)}`, pLowX + 4, yBottom - 6);

              // Spot price (red dashed)
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

              // Predicted median (green dashed)
              if (predicted != null) {
                const predIdx = findIdx(prices, predicted);
                const predX = xScale.getPixelForValue(predIdx);
                const predCdf = cdf[predIdx] ?? 0.5;
                const predY = yScale.getPixelForValue(predCdf);

                ctx.strokeStyle = "#2ecc71";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(predX, yTop);
                ctx.lineTo(predX, yBottom);
                ctx.stroke();

                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(xLeft, predY);
                ctx.lineTo(predX, predY);
                ctx.stroke();

                ctx.fillStyle = "#2ecc71";
                ctx.setLineDash([]);
                ctx.fillText(
                  `Predicted $${predicted.toFixed(0)} (${(predCdf * 100).toFixed(0)}%)`,
                  predX + 4,
                  yTop + 42,
                );
              }

              // Realized price (cyan solid)
              if (realized != null) {
                const realIdx = findIdx(prices, realized);
                const realX = xScale.getPixelForValue(realIdx);
                const cdfVal = cdf[realIdx] ?? 0;
                const realY = yScale.getPixelForValue(cdfVal);

                ctx.strokeStyle = "#00d2ff";
                ctx.lineWidth = 2;
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(realX, yTop);
                ctx.lineTo(realX, yBottom);
                ctx.stroke();

                ctx.setLineDash([4, 3]);
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(xLeft, realY);
                ctx.lineTo(realX, realY);
                ctx.stroke();

                ctx.fillStyle = "#00d2ff";
                ctx.setLineDash([]);
                ctx.fillText(
                  `Actual $${realized.toFixed(0)} (${(cdfVal * 100).toFixed(0)}%)`,
                  realX + 4,
                  yTop + 28,
                );
              }

              ctx.restore();
            },
          },
        }}
      />
    </div>
  );
});
