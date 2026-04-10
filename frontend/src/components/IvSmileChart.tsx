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
import type { IvSmile } from "../types/prediction";

ChartJS.register(
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Legend
);

interface Props {
  ivSmile: IvSmile;
  spot: number;
}

function findIdx(prices: number[], target: number): number {
  return prices.reduce(
    (best, p, i) => (Math.abs(p - target) < Math.abs(prices[best] - target) ? i : best),
    0
  );
}

export default function IvSmileChart({ ivSmile, spot }: Props) {
  // Downsample smooth curve
  const step = Math.max(1, Math.floor(ivSmile.smooth_strikes.length / 500));
  const smoothStrikes = ivSmile.smooth_strikes.filter((_, i) => i % step === 0);
  const smoothIv = ivSmile.smooth_iv.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 15, color: "#ccc" }}>
        Implied Volatility Smile
      </h3>
      <p style={{ margin: "0 0 12px", fontSize: 11, color: "#666" }}>
        Market-implied volatility at each strike. The shape reveals risk perception:
        a left skew (higher IV for low strikes) indicates crash fear; a flat smile suggests
        symmetric expectations. {ivSmile.n_strikes} strikes with valid IV.
      </p>
      <Line
        data={{
          labels: smoothStrikes.map((s) => s.toFixed(1)),
          datasets: [
            {
              label: "Smoothed IV (B-spline)",
              data: smoothIv.map((v) => v * 100),
              borderColor: "#a882ff",
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
            },
            {
              label: `Raw IV (${ivSmile.n_strikes} strikes)`,
              data: smoothStrikes.map((s) => {
                const idx = ivSmile.raw_strikes.findIndex(
                  (rs) => Math.abs(rs - s) < (ivSmile.raw_strikes[1] - ivSmile.raw_strikes[0]) * 0.6
                );
                return idx >= 0 ? ivSmile.raw_iv[idx] * 100 : null;
              }),
              borderColor: "transparent",
              backgroundColor: "rgba(168, 130, 255, 0.5)",
              pointRadius: 4,
              pointStyle: "circle",
              showLine: false,
            },
          ],
        }}
        options={{
          responsive: true,
          plugins: {
            legend: {
              display: true,
              labels: { color: "#888", font: { size: 10 } },
              position: "top",
            },
            tooltip: {
              callbacks: {
                title: (items) => `Strike: $${items[0].label}`,
                label: (item) => `IV: ${Number(item.raw).toFixed(1)}%`,
              },
            },
          },
          scales: {
            x: {
              type: "category",
              title: { display: true, text: "Strike Price ($)", color: "#888" },
              ticks: { color: "#666", maxTicksLimit: 10 },
              grid: { color: "#222" },
            },
            y: {
              title: { display: true, text: "Implied Volatility (%)", color: "#888" },
              ticks: {
                color: "#666",
                callback: (v) => `${Number(v).toFixed(0)}%`,
              },
              grid: { color: "#222" },
            },
          },
          animation: {
            onComplete: ({ chart }) => {
              const ctx = chart.ctx;
              const xScale = chart.scales.x;
              const yTop = chart.chartArea.top;
              const yBottom = chart.chartArea.bottom;

              // ATM line at spot
              const spotX = xScale.getPixelForValue(findIdx(smoothStrikes, spot));
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
              ctx.fillText(`ATM $${spot.toFixed(0)}`, spotX + 4, yTop + 14);
              ctx.restore();
            },
          },
        }}
      />
    </div>
  );
}
