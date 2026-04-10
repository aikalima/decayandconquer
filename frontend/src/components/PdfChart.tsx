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
}

function findIdx(prices: number[], target: number): number {
  return prices.reduce(
    (best, p, i) => (Math.abs(p - target) < Math.abs(prices[best] - target) ? i : best),
    0
  );
}

export default function PdfChart({ data, spot, realized, predicted }: Props) {
  const step = Math.max(1, Math.floor(data.prices.length / 500));
  const prices = data.prices.filter((_, i) => i % step === 0);
  const pdf = data.pdf.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16 }}>
      <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#ccc" }}>
        Probability Density
      </h3>
      <Line
        data={{
          labels: prices.map((p) => p.toFixed(1)),
          datasets: [
            {
              label: "PDF",
              data: pdf,
              borderColor: "#4a90d9",
              backgroundColor: "rgba(74, 144, 217, 0.1)",
              fill: true,
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
              title: { display: true, text: "Probability Density (per $)", color: "#888" },
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

              // Spot price line (red dashed)
              const spotX = xScale.getPixelForValue(findIdx(prices, spot));
              ctx.save();
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

              // Predicted median line (yellow dashed)
              if (predicted != null) {
                const predX = xScale.getPixelForValue(findIdx(prices, predicted));
                ctx.strokeStyle = "#f1c40f";
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(predX, yTop);
                ctx.lineTo(predX, yBottom);
                ctx.stroke();
                ctx.fillStyle = "#f1c40f";
                ctx.fillText(`Predicted $${predicted.toFixed(0)}`, predX + 4, yTop + 42);
                ctx.setLineDash([]);
              }

              // Realized price line (solid green)
              if (realized != null) {
                const realX = xScale.getPixelForValue(findIdx(prices, realized));
                ctx.strokeStyle = "#2ecc71";
                ctx.lineWidth = 2;
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.moveTo(realX, yTop);
                ctx.lineTo(realX, yBottom);
                ctx.stroke();
                ctx.fillStyle = "#2ecc71";
                ctx.fillText(`Actual $${realized.toFixed(0)}`, realX + 4, yTop + 28);
              }

              ctx.restore();
            },
          },
        }}
      />
    </div>
  );
}
