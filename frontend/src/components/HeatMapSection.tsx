import { useState, useEffect } from "react";
import { fetchHeatMapStream } from "../api/client";
import type { HeatMapCell, HeatMapResponse } from "../api/client";

type Metric = "net_volume" | "net_oi" | "net_premium";

const METRICS: { key: Metric; label: string; tooltip: string }[] = [
  { key: "net_volume", label: "Volume", tooltip: "Call volume minus put volume" },
  { key: "net_oi", label: "Open Interest", tooltip: "Call OI minus put OI" },
  { key: "net_premium", label: "Net Premium", tooltip: "Call premium minus put premium (volume-weighted)" },
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
  const t = Math.pow(intensity, 0.6);
  if (value > 0) {
    return `rgb(${Math.round(10 + t * 36)}, ${Math.round(30 + t * 174)}, ${Math.round(10 + t * 103)})`;
  } else {
    return `rgb(${Math.round(30 + t * 201)}, ${Math.round(10 + t * 66)}, ${Math.round(10 + t * 50)})`;
  }
}

interface Props {
  ticker: string;
}

export default function HeatMapSection({ ticker }: Props) {
  const [data, setData] = useState<HeatMapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [metric, setMetric] = useState<Metric>("net_volume");
  const [hoveredCell, setHoveredCell] = useState<HeatMapCell | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const [fetchedTicker, setFetchedTicker] = useState("");

  // Auto-fetch when ticker changes
  useEffect(() => {
    if (!ticker || ticker === fetchedTicker) return;
    setLoading(true);
    setData(null);
    setStage("Loading heat map...");
    fetchHeatMapStream(ticker, 4, (event) => {
      if (event.stage) setStage(event.stage);
    })
      .then((res) => {
        if (!res.error) setData(res);
        setFetchedTicker(ticker);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [ticker]); // eslint-disable-line react-hooks/exhaustive-deps

  const cellMap = new Map<string, HeatMapCell>();
  let maxAbs = 0;
  if (data) {
    for (const c of data.cells) {
      cellMap.set(`${c.strike}-${c.expiry}`, c);
      const v = Math.abs(c[metric]);
      if (v > maxAbs) maxAbs = v;
    }
  }

  const atmStrike = data ? data.strikes.reduce((best, s) =>
    Math.abs(s - data.spot) < Math.abs(best - data.spot) ? s : best, data.strikes[0]) : 0;

  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16, position: "relative" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h3 style={{ margin: 0, fontSize: 15, color: "#ccc" }}>Options Heat Map</h3>
        <div style={{ display: "flex", gap: 4 }}>
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              title={m.tooltip}
              style={{
                padding: "3px 8px",
                borderRadius: 4,
                border: `1px solid ${metric === m.key ? "#6c63ff" : "#333"}`,
                background: metric === m.key ? "#6c63ff" : "transparent",
                color: metric === m.key ? "#fff" : "#888",
                cursor: "pointer",
                fontSize: 10,
                fontWeight: 600,
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p style={{ margin: "0 0 12px", fontSize: 11, color: "#666" }}>
        Call vs put activity across strikes and expiry dates.
        Green = bullish (call-heavy), red = bearish (put-heavy).
      </p>

      {loading && (
        <div style={{ padding: "20px 0", textAlign: "center", color: "#555", fontSize: 12 }}>
          {stage || "Working..."}
        </div>
      )}

      {!loading && !data && (
        <div style={{ padding: "20px 0", textAlign: "center", color: "#444", fontSize: 12 }}>
          No heat map data available.
        </div>
      )}

      {data && (
        <>
          <div style={{ fontSize: 11, color: "#666", marginBottom: 8 }}>
            Spot: ${data.spot.toFixed(2)} | {data.expiries.length} expiries, {data.strikes.length} strikes
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
                            onMouseEnter={(e) => { if (cell) { setHoveredCell(cell); setHoverPos({ x: e.clientX, y: e.clientY }); } }}
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

          {/* Legend */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, justifyContent: "center" }}>
            <span style={{ fontSize: 10, color: "#e74c3c" }}>Put-heavy</span>
            <div style={{
              width: 160,
              height: 8,
              borderRadius: 4,
              background: "linear-gradient(90deg, #e74c3c, #3d0a0a, #0f0f1a, #0a3d0a, #2ecc71)",
            }} />
            <span style={{ fontSize: 10, color: "#2ecc71" }}>Call-heavy</span>
          </div>

          {/* Tooltip */}
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
            </div>
          )}
        </>
      )}
    </div>
  );
}
