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
  const color = value > 0 ? "var(--up)" : "var(--down)";
  return `color-mix(in srgb, ${color} ${Math.round(18 + t * 72)}%, transparent)`;
}

interface Props {
  ticker: string;
}

export default function HeatMapSection({ ticker }: Props) {
  const [data, setData] = useState<HeatMapResponse | null>(null);
  const [stage, setStage] = useState("");
  const [metric, setMetric] = useState<Metric>("net_volume");
  const [hoveredCell, setHoveredCell] = useState<HeatMapCell | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const [fetchedTicker, setFetchedTicker] = useState("");
  const [nowMs] = useState(() => Date.now());
  const loading = Boolean(ticker && ticker !== fetchedTicker);

  // Auto-fetch when ticker changes
  useEffect(() => {
    if (!ticker || ticker === fetchedTicker) return;
    fetchHeatMapStream(ticker, 4, (event) => {
      if (event.stage) setStage(event.stage);
    })
      .then((res) => {
        if (!res.error) setData(res);
        setFetchedTicker(ticker);
      })
      .catch(() => {
        setData(null);
        setFetchedTicker(ticker);
      });
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
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, position: "relative", boxShadow: "var(--shadow-soft)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h3 className="dashboard-section-title">Options Heat Map</h3>
        <div style={{ display: "flex", gap: 4 }}>
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              title={m.tooltip}
              style={{
                padding: "5px 10px",
                borderRadius: 4,
                border: `1px solid ${metric === m.key ? "var(--brand)" : "var(--border)"}`,
                background: metric === m.key ? "var(--brand)" : "transparent",
                color: metric === m.key ? "var(--text-on-accent)" : "var(--muted)",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 750,
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <p className="dashboard-caption" style={{ margin: "0 0 14px" }}>
        Call vs put activity across strikes and expiry dates.
        Green marks call-heavy positioning; red marks put-heavy positioning.
      </p>

      {loading && (
        <div style={{ padding: "20px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
          {stage || "Loading heat map..."}
        </div>
      )}

      {!loading && !data && (
        <div style={{ padding: "20px 0", textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
          No heat map data available.
        </div>
      )}

      {data && (
        <>
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10 }}>
            Spot: ${data.spot.toFixed(2)} | {data.expiries.length} expiries, {data.strikes.length} strikes
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ padding: "7px 8px", textAlign: "left", color: "var(--muted)", fontSize: 11, borderBottom: "1px solid var(--border)" }}>
                    Expiry
                  </th>
                  {data.strikes.map((s) => (
                    <th
                      key={s}
                      style={{
                        padding: "6px 4px",
                        textAlign: "center",
                        color: s === atmStrike ? "var(--brand)" : "var(--muted)",
                        fontSize: 11,
                        fontWeight: s === atmStrike ? 700 : 400,
                        borderBottom: s === atmStrike ? "2px solid var(--brand)" : "1px solid var(--border)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      ${formatStrike(s)}
                      {s === atmStrike && <div style={{ fontSize: 9, color: "var(--brand)" }}>ATM</div>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.expiries.map((exp) => {
                  const days = Math.round((new Date(exp + "T00:00:00").getTime() - nowMs) / 86400000);
                  return (
                    <tr key={exp}>
                      <td style={{
                        padding: "6px 8px",
                        color: "var(--text-soft)",
                        fontSize: 11,
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                        borderBottom: "1px solid var(--border)",
                      }}>
                        {formatExpiry(exp)} <span style={{ color: "var(--muted)" }}>({days}d)</span>
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
                              color: Math.abs(value) > maxAbs * 0.3 ? "var(--text-on-accent)" : "var(--muted)",
                              fontSize: 10,
                              fontWeight: Math.abs(value) > maxAbs * 0.5 ? 700 : 400,
                              borderBottom: "1px solid var(--surface)",
                              borderRight: "1px solid var(--surface)",
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
            <span style={{ fontSize: 11, color: "var(--down)" }}>Put-heavy</span>
            <div style={{
              width: 160,
              height: 8,
              borderRadius: 4,
              background: "linear-gradient(90deg, var(--down), var(--down-tint), var(--input-bg), var(--up-tint), var(--up))",
            }} />
            <span style={{ fontSize: 11, color: "var(--up)" }}>Call-heavy</span>
          </div>

          {/* Tooltip */}
          {hoveredCell && (
            <div
              style={{
                position: "fixed",
                left: hoverPos.x + 12,
                top: hoverPos.y - 10,
                background: "var(--surface-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "10px 12px",
                fontSize: 12,
                color: "var(--text-soft)",
                zIndex: 1000,
                boxShadow: "var(--shadow)",
                pointerEvents: "none",
                lineHeight: 1.6,
              }}
            >
              <div style={{ fontWeight: 800, color: "var(--text)", marginBottom: 4 }}>
                ${hoveredCell.strike.toFixed(0)} | {hoveredCell.expiry}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "auto auto auto", gap: "2px 12px" }}>
                <span style={{ color: "var(--muted)" }}></span>
                <span style={{ color: "var(--up)", fontWeight: 700 }}>Calls</span>
                <span style={{ color: "var(--down)", fontWeight: 700 }}>Puts</span>
                <span style={{ color: "var(--muted)" }}>Volume</span>
                <span>{hoveredCell.call_volume.toLocaleString()}</span>
                <span>{hoveredCell.put_volume.toLocaleString()}</span>
                <span style={{ color: "var(--muted)" }}>OI</span>
                <span>{hoveredCell.call_oi.toLocaleString()}</span>
                <span>{hoveredCell.put_oi.toLocaleString()}</span>
                <span style={{ color: "var(--muted)" }}>Mid</span>
                <span>${hoveredCell.call_mid.toFixed(2)}</span>
                <span>${hoveredCell.put_mid.toFixed(2)}</span>
                <span style={{ color: "var(--muted)" }}>IV</span>
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
