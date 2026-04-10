import {
  Chart as ChartJS,
  LineElement,
  PointElement,
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
}

function findIdx(prices: number[], target: number): number {
  return prices.reduce(
    (best, p, i) => (Math.abs(p - target) < Math.abs(prices[best] - target) ? i : best),
    0
  );
}

export default function CdfChart({ data, spot, realized, predicted }: Props) {
  const step = Math.max(1, Math.floor(data.prices.length / 500));
  const prices = data.prices.filter((_, i) => i % step === 0);
  const cdf = data.cdf.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16 }}>
      <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#ccc" }}>
        Cumulative Distribution
      </h3>
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

              ctx.save();

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

              // Predicted median (yellow dashed)
              if (predicted != null) {
                const predIdx = findIdx(prices, predicted);
                const predX = xScale.getPixelForValue(predIdx);
                const predCdf = cdf[predIdx] ?? 0.5;
                const predY = yScale.getPixelForValue(predCdf);

                ctx.strokeStyle = "#f1c40f";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(predX, yTop);
                ctx.lineTo(predX, yBottom);
                ctx.stroke();

                // Horizontal to Y axis
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(chart.chartArea.left, predY);
                ctx.lineTo(predX, predY);
                ctx.stroke();

                ctx.fillStyle = "#f1c40f";
                ctx.setLineDash([]);
                ctx.fillText(
                  `Predicted $${predicted.toFixed(0)} (${(predCdf * 100).toFixed(0)}%)`,
                  predX + 4,
                  yTop + 42,
                );
              }

              // Realized price (solid green)
              if (realized != null) {
                const realIdx = findIdx(prices, realized);
                const realX = xScale.getPixelForValue(realIdx);
                const cdfVal = cdf[realIdx] ?? 0;
                const realY = yScale.getPixelForValue(cdfVal);

                ctx.strokeStyle = "#2ecc71";
                ctx.lineWidth = 2;
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(realX, yTop);
                ctx.lineTo(realX, yBottom);
                ctx.stroke();

                // Horizontal line to Y axis
                ctx.setLineDash([4, 3]);
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(chart.chartArea.left, realY);
                ctx.lineTo(realX, realY);
                ctx.stroke();

                ctx.fillStyle = "#2ecc71";
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
}
