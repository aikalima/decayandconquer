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
  // Downsample to ~500 points
  const step = Math.max(1, Math.floor(greeks.strikes.length / 500));
  const strikes = greeks.strikes.filter((_, i) => i % step === 0);
  const delta = greeks.delta.filter((_, i) => i % step === 0);
  const gamma = greeks.gamma.filter((_, i) => i % step === 0);
  const theta = greeks.theta.filter((_, i) => i % step === 0);
  const vega = greeks.vega.filter((_, i) => i % step === 0);

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, minHeight: 300 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 15, color: "#ccc" }}>
        Option Greeks
      </h3>
      <p style={{ margin: "0 0 12px", fontSize: 11, color: "#666" }}>
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
              borderColor: "#3498db",
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y",
            },
            {
              label: "Gamma",
              data: gamma,
              borderColor: "#2ecc71",
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y1",
            },
            {
              label: "Theta ($/day)",
              data: theta,
              borderColor: "#e74c3c",
              pointRadius: 0,
              borderWidth: 2,
              tension: 0.3,
              yAxisID: "y1",
            },
            {
              label: "Vega ($/1% IV)",
              data: vega,
              borderColor: "#f39c12",
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
              labels: { color: "#888", font: { size: 10 } },
              position: "top",
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
              title: { display: true, text: "Strike Price ($)", color: "#888" },
              ticks: { color: "#666", maxTicksLimit: 10 },
              grid: { color: "#222" },
            },
            y: {
              type: "linear",
              position: "left",
              title: { display: true, text: "Delta", color: "#3498db" },
              ticks: { color: "#666" },
              grid: { color: "#222" },
              min: 0,
              max: 1,
            },
            y1: {
              type: "linear",
              position: "right",
              title: { display: true, text: "Gamma / Theta / Vega", color: "#888" },
              ticks: { color: "#666" },
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
});
