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
import type { Greeks } from "../types/prediction";
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
  greeks: Greeks;
  spot: number;
}

function findIdx(prices: number[], target: number): number {
  return prices.reduce(
    (best, p, i) => (Math.abs(p - target) < Math.abs(prices[best] - target) ? i : best),
    0
  );
}

export default React.memo(function GreeksChart({ greeks, spot }: Props) {
  const colors = useChartTheme();
  // Downsample to ~500 points
  const step = Math.max(1, Math.floor(greeks.strikes.length / 500));
  const strikes = greeks.strikes.filter((_, i) => i % step === 0);
  const delta = greeks.delta.filter((_, i) => i % step === 0);
  const gamma = greeks.gamma.filter((_, i) => i % step === 0);
  const theta = greeks.theta.filter((_, i) => i % step === 0);
  const vega = greeks.vega.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, minHeight: 320, boxShadow: "var(--shadow-soft)" }}>
      <h3 className="dashboard-section-title" style={{ marginBottom: 4 }}>
        Option Greeks
      </h3>
      <p className="dashboard-caption" style={{ margin: "0 0 14px" }}>
        Sensitivity of option prices to underlying factors across strikes.
        Delta measures directional exposure, gamma its rate of change,
        theta the daily time decay, and vega the sensitivity to implied volatility.
      </p>
      <Line
        data={{
          labels: strikes.map((s) => s.toFixed(1)),
          datasets: [
            {
              label: "Delta",
              data: delta,
              borderColor: colors.brand,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y",
            },
            {
              label: "Gamma",
              data: gamma,
              borderColor: colors.brandStrong,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y1",
            },
            {
              label: "Theta ($/day)",
              data: theta,
              borderColor: colors.risk,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y1",
            },
            {
              label: "Vega ($/1% IV)",
              data: vega,
              borderColor: colors.subtle,
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y1",
            },
          ],
        }}
        options={{
          responsive: true,
          interaction: {
            mode: "index",
            intersect: false,
          },
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
                label: (item) => `${item.dataset.label}: ${Number(item.raw).toFixed(4)}`,
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
              type: "linear",
              position: "left",
              title: { display: true, text: "Delta", color: colors.brand, font: { size: 12, weight: 600 } },
              ticks: { color: colors.subtle, font: { size: 12 } },
              grid: { color: colors.grid },
              min: 0,
              max: 1,
            },
            y1: {
              type: "linear",
              position: "right",
              title: { display: true, text: "Gamma / Theta / Vega", color: colors.muted, font: { size: 12, weight: 600 } },
              ticks: { color: colors.subtle, font: { size: 12 } },
              grid: { drawOnChartArea: false },
            },
          },
          animation: {
            onComplete: ({ chart }) => {
              const ctx = chart.ctx;
              const xScale = chart.scales.x;
              const yTop = chart.chartArea.top;
              const yBottom = chart.chartArea.bottom;

              const spotX = xScale.getPixelForValue(findIdx(strikes, spot));
              ctx.save();
              ctx.strokeStyle = colors.risk;
              ctx.lineWidth = 1.5;
              ctx.setLineDash([6, 4]);
              ctx.beginPath();
              ctx.moveTo(spotX, yTop);
              ctx.lineTo(spotX, yBottom);
              ctx.stroke();
              ctx.fillStyle = colors.risk;
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
