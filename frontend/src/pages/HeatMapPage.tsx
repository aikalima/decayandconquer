import { useState } from "react";
import ProgressBar from "../components/ProgressBar";
import { fetchHeatMapStream } from "../api/client";
import type { HeatMapCell, HeatMapResponse } from "../api/client";

type Metric = "net_volume" | "net_oi" | "net_premium";

const METRICS: { key: Metric; label: string; tooltip: string }[] = [
  { key: "net_volume", label: "Volume", tooltip: "Call volume minus put volume. Green = more call activity." },
  { key: "net_oi", label: "Open Interest", tooltip: "Call OI minus put OI. Green = more open call positions." },
  { key: "net_premium", label: "Net Premium", tooltip: "Call premium minus put premium (volume-weighted). Green = more bullish dollar flow." },
];

function formatStrike(s: number): string {
  return s >= 1000 ? `${(s / 1000).toFixed(1)}K` : s.toFixed(0);
}

function formatExpiry(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = d.getDate();
  const suffix = day === 1 || day === 21 || day === 31 ? "st" : day === 2 || day === 22 ? "nd" : day === 3 || day === 23 ? "rd" : "th";
  return `${months[d.getMonth()]} ${day}${suffix}`;
}

function formatCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(0);
}

function cellColor(value: number, maxAbs: number): string {
  if (maxAbs === 0 || value === 0) return "transparent";
  const intensity = Math.min(Math.abs(value) / maxAbs, 1);
  const t = Math.pow(intensity, 0.6); // gamma for better visual spread
  if (value > 0) {
    const r = Math.round(10 + t * 36);
    const g = Math.round(30 + t * 174);
    const b = Math.round(10 + t * 103);
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    const r = Math.round(30 + t * 201);
    const g = Math.round(10 + t * 66);
    const b = Math.round(10 + t * 50);
    return `rgb(${r}, ${g}, ${b})`;
  }
}

export default function HeatMapPage() {
  const [ticker, setTicker] = useState("SPY");
  const [data, setData] = useState<HeatMapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("net_volume");
  const [hoveredCell, setHoveredCell] = useState<HeatMapCell | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setData(null);
    setProgress(0);
    setStage("Working...");

    try {
      const res = await fetchHeatMapStream(ticker, 6, (event) => {
        if (event.stage) setStage(event.stage);
        setProgress(event.progress);
      });
      if (res.error) {
        setError(res.error);
      } else {
        setData(res);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  // Build cell lookup map
  const cellMap = new Map<string, HeatMapCell>();
  if (data) {
    for (const c of data.cells) {
      cellMap.set(`${c.strike}-${c.expiry}`, c);
    }
  }

  // Compute max absolute value for color scaling
  let maxAbs = 0;
  if (data) {
    for (const c of data.cells) {
      const v = Math.abs(c[metric]);
      if (v > maxAbs) maxAbs = v;
    }
  }

  // ATM strike index
  const atmStrike = data ? data.strikes.reduce((best, s) =>
    Math.abs(s - data.spot) < Math.abs(best - data.spot) ? s : best, data.strikes[0]) : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ maxWidth: "70%" }}>
        <p style={{ margin: 0, fontSize: 13, color: "#888", lineHeight: 1.6 }}>
          Visualize call vs put activity across strikes and expiry dates.
          Green cells indicate bullish (call-heavy) positioning, red cells indicate bearish (put-heavy).
        </p>
      </div>

      {/* Controls */}
      <div style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
      }}>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid #333",
            background: "#0f0f1a",
            color: "#e0e0e0",
            fontSize: 14,
            fontWeight: 600,
            width: 80,
            textAlign: "center",
          }}
        />

        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              title={m.tooltip}
              style={{
                padding: "4px 10px",
                borderRadius: 4,
                border: `1px solid ${metric === m.key ? "#6c63ff" : "#333"}`,
                background: metric === m.key ? "#6c63ff" : "transparent",
                color: metric === m.key ? "#fff" : "#888",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          style={{
            padding: "8px 24px",
            borderRadius: 6,
            border: "none",
            background: loading ? "#333" : "#6c63ff",
            color: loading ? "#666" : "#fff",
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: 14,
            fontWeight: 600,
            marginLeft: "auto",
          }}
        >
          {loading ? "Working..." : "Generate"}
        </button>
      </div>

      {/* Progress */}
      {loading && <ProgressBar progress={progress} stage={stage} />}

      {error && (
        <div style={{
          background: "#2e1a1a",
          border: "1px solid #5a2020",
          borderRadius: 8,
          padding: 12,
          color: "#e74c3c",
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Heat Map Grid */}
      {data && (
        <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, position: "relative" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, color: "#ccc" }}>
                {data.ticker} Options Heat Map
              </h3>
              <span style={{ fontSize: 11, color: "#666" }}>
                Spot: ${data.spot.toFixed(2)} | {data.expiries.length} expiries, {data.strikes.length} strikes | {data.fetch_time_seconds}s
              </span>
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ padding: "6px 8px", textAlign: "left", color: "#666", fontSize: 10, borderBottom: "1px solid #2a2a4a" }}>
                    Expiry
                  </th>
                  {data.strikes.map((s) => (
                    <th
                      key={s}
                      style={{
                        padding: "6px 4px",
                        textAlign: "center",
                        color: s === atmStrike ? "#6c63ff" : "#666",
                        fontSize: 10,
                        fontWeight: s === atmStrike ? 700 : 400,
                        borderBottom: s === atmStrike ? "2px solid #6c63ff" : "1px solid #2a2a4a",
                        whiteSpace: "nowrap",
                      }}
                    >
                      ${formatStrike(s)}
                      {s === atmStrike && <div style={{ fontSize: 8, color: "#6c63ff" }}>ATM</div>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.expiries.map((exp) => {
                  const days = Math.round((new Date(exp + "T00:00:00").getTime() - Date.now()) / 86400000);
                  return (
                    <tr key={exp}>
                      <td style={{
                        padding: "6px 8px",
                        color: "#aaa",
                        fontSize: 10,
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                        borderBottom: "1px solid #1a1a2e",
                      }}>
                        {formatExpiry(exp)} <span style={{ color: "#555" }}>({days}d)</span>
                      </td>
                      {data.strikes.map((s) => {
                        const cell = cellMap.get(`${s}-${exp}`);
                        const value = cell ? cell[metric] : 0;
                        return (
                          <td
                            key={s}
                            onMouseEnter={(e) => {
                              if (cell) {
                                setHoveredCell(cell);
                                setHoverPos({ x: e.clientX, y: e.clientY });
                              }
                            }}
                            onMouseLeave={() => setHoveredCell(null)}
                            style={{
                              padding: "4px 2px",
                              textAlign: "center",
                              background: cellColor(value, maxAbs),
                              color: Math.abs(value) > maxAbs * 0.3 ? "#fff" : "#666",
                              fontSize: 9,
                              fontWeight: Math.abs(value) > maxAbs * 0.5 ? 700 : 400,
                              borderBottom: "1px solid #0f0f1a",
                              borderRight: "1px solid #0f0f1a",
                              cursor: cell ? "crosshair" : "default",
                              minWidth: 40,
                            }}
                          >
                            {value !== 0 ? formatCompact(value) : ""}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Color legend */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, justifyContent: "center" }}>
            <span style={{ fontSize: 10, color: "#e74c3c" }}>Put-heavy (bearish)</span>
            <div style={{
              width: 200,
              height: 10,
              borderRadius: 5,
              background: "linear-gradient(90deg, #e74c3c, #3d0a0a, #0f0f1a, #0a3d0a, #2ecc71)",
            }} />
            <span style={{ fontSize: 10, color: "#2ecc71" }}>Call-heavy (bullish)</span>
          </div>

          {/* Hover tooltip */}
          {hoveredCell && (
            <div
              style={{
                position: "fixed",
                left: hoverPos.x + 12,
                top: hoverPos.y - 10,
                background: "#16162a",
                border: "1px solid #2a2a4a",
                borderRadius: 8,
                padding: "10px 12px",
                fontSize: 11,
                color: "#ccc",
                zIndex: 1000,
                boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
                pointerEvents: "none",
                lineHeight: 1.6,
              }}
            >
              <div style={{ fontWeight: 700, color: "#fff", marginBottom: 4 }}>
                ${hoveredCell.strike.toFixed(0)} | {hoveredCell.expiry}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "auto auto auto", gap: "2px 12px" }}>
                <span style={{ color: "#888" }}></span>
                <span style={{ color: "#2ecc71", fontWeight: 600 }}>Calls</span>
                <span style={{ color: "#e74c3c", fontWeight: 600 }}>Puts</span>

                <span style={{ color: "#888" }}>Volume</span>
                <span>{hoveredCell.call_volume.toLocaleString()}</span>
                <span>{hoveredCell.put_volume.toLocaleString()}</span>

                <span style={{ color: "#888" }}>OI</span>
                <span>{hoveredCell.call_oi.toLocaleString()}</span>
                <span>{hoveredCell.put_oi.toLocaleString()}</span>

                <span style={{ color: "#888" }}>Mid</span>
                <span>${hoveredCell.call_mid.toFixed(2)}</span>
                <span>${hoveredCell.put_mid.toFixed(2)}</span>

                <span style={{ color: "#888" }}>IV</span>
                <span>{(hoveredCell.call_iv * 100).toFixed(1)}%</span>
                <span>{(hoveredCell.put_iv * 100).toFixed(1)}%</span>
              </div>
              <div style={{ marginTop: 4, borderTop: "1px solid #2a2a4a", paddingTop: 4 }}>
                <span style={{ color: "#888" }}>Net Premium: </span>
                <span style={{ color: hoveredCell.net_premium > 0 ? "#2ecc71" : "#e74c3c", fontWeight: 600 }}>
                  ${formatCompact(hoveredCell.net_premium)}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
