import type { MarketEvent } from "../api/client";

interface Props {
  events: MarketEvent[];
  loading: boolean;
  disclaimer?: string;
  hoveredIndex?: number | null;
  onHover?: (index: number | null) => void;
}

import { CATEGORY_COLORS } from "./categoryColors";

export default function MarketContext({ events, loading, disclaimer, hoveredIndex, onHover }: Props) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, boxShadow: "var(--shadow-soft)" }}>
      <h3 className="dashboard-section-title" style={{ marginBottom: 4 }}>
        Market Context
      </h3>
      <p className="dashboard-caption" style={{ margin: "0 0 14px" }}>
        Key events during the observation period that may have influenced options pricing.
      </p>

      {loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              style={{
                height: 48,
                borderRadius: 6,
                background: "linear-gradient(90deg, var(--surface-subtle) 25%, var(--surface-hover) 50%, var(--surface-subtle) 75%)",
                backgroundSize: "200% 100%",
                animation: "shimmer 1.5s infinite",
              }}
            />
          ))}
          <style>{`
            @keyframes shimmer {
              0% { background-position: 200% 0; }
              100% { background-position: -200% 0; }
            }
          `}</style>
        </div>
      )}

      {!loading && events.length === 0 && (
        <div style={{ fontSize: 13, color: "var(--muted)", padding: "8px 0" }}>
          No significant events identified for this period.
        </div>
      )}

      {!loading && events.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {events.map((event, i) => {
            const isHovered = hoveredIndex === i;
            const catColor = CATEGORY_COLORS[event.category] || "var(--muted)";
            return (
            <div
              key={i}
              onMouseEnter={() => onHover?.(i)}
              onMouseLeave={() => onHover?.(null)}
              style={{
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
                padding: "8px 10px",
                background: isHovered ? "var(--surface-hover)" : "var(--surface-subtle)",
                borderRadius: 6,
                borderLeft: `3px solid ${catColor}`,
                boxShadow: isHovered ? `inset 3px 0 12px -2px ${catColor}88` : undefined,
                transition: "background 0.15s, box-shadow 0.15s",
                cursor: "default",
              }}
            >
              <div style={{ minWidth: 70, flexShrink: 0 }}>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "monospace" }}>
                  {event.date}
                </div>
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 600,
                    color: CATEGORY_COLORS[event.category] || "var(--muted)",
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  {event.category}
                </span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 750, marginBottom: 3 }}>
                  {event.headline}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45 }}>
                  {event.impact}
                  {event.source && (
                    <span style={{ color: "var(--muted-2)", marginLeft: 4 }}>({event.source})</span>
                  )}
                </div>
              </div>
            </div>
            );
          })}
        </div>
      )}

      {disclaimer && !loading && (
        <div style={{ fontSize: 11, color: "var(--muted-2)", marginTop: 10, fontStyle: "italic" }}>
          {disclaimer}
        </div>
      )}
    </div>
  );
}
