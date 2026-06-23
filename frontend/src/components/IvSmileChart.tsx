import React from "react";
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
import { useChartTheme } from "../themeContext";

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

export default React.memo(function IvSmileChart({ ivSmile, spot }: Props) {
  const colors = useChartTheme();
  // Downsample smooth curve
  const step = Math.max(1, Math.floor(ivSmile.smooth_strikes.length / 500));
  const smoothStrikes = ivSmile.smooth_strikes.filter((_, i) => i % step === 0);
  const smoothIv = ivSmile.smooth_iv.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, minHeight: 320, boxShadow: "var(--shadow-soft)" }}>
      <h3 className="dashboard-section-title" style={{ marginBottom: 4 }}>
        Implied Volatility
      </h3>
      <p className="dashboard-caption" style={{ margin: "0 0 14px" }}>
        Market-implied volatility at each strike. The shape reveals risk perception:
        a left skew (higher IV for low strikes) indicates crash fear; a flat smile suggests
        symmetric expectations. {ivSmile.n_strikes} strikes with valid IV.
      </p>
      <Line
        data={{
          labels: smoothStrikes.map((s) => s.toFixed(1)),
          datasets: [
            {
              label: "Implied Volatility",
              data: smoothIv.map((v) => v * 100),
              borderColor: colors.accent,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
            },
          ],
        }}
        options={{
          responsive: true,
          plugins: {
            legend: {
              display: true,
              labels: { color: colors.muted, font: { size: 12 } },
              position: "top",
              onClick: () => {},
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
              title: { display: true, text: "Strike Price ($)", color: colors.muted, font: { size: 12, weight: 600 } },
              ticks: { color: colors.subtle, maxTicksLimit: 10, font: { size: 12 } },
              grid: { color: colors.grid },
            },
            y: {
              title: { display: true, text: "Implied Volatility (%)", color: colors.muted, font: { size: 12, weight: 600 } },
              ticks: {
                color: colors.subtle,
                font: { size: 12 },
                callback: (v) => `${Number(v).toFixed(0)}%`,
              },
              grid: { color: colors.grid },
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
              ctx.strokeStyle = colors.danger;
              ctx.lineWidth = 1.5;
              ctx.setLineDash([6, 4]);
              ctx.beginPath();
              ctx.moveTo(spotX, yTop);
              ctx.lineTo(spotX, yBottom);
              ctx.stroke();
              ctx.fillStyle = colors.danger;
              ctx.font = "12px sans-serif";
              ctx.fillText(`ATM $${spot.toFixed(0)}`, spotX + 4, yTop + 14);
              ctx.restore();
            },
          },
        }}
      />
    </div>
  );
});
