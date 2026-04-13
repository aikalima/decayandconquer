import { useState, useEffect } from "react";
import { fetchThetaPlays, fetchThetaExpiries } from "../api/client";
import type { ThetaPlayRow, ThetaPlaysResponse, ThetaExpiry } from "../api/client";

type Tab = "highest_premium" | "expensive_calls" | "expensive_puts";

const TABS: { key: Tab; label: string; description: string }[] = [
  { key: "highest_premium", label: "Highest Premium", description: "Best candidates for iron condors. Options with the highest IV/HV ratio overall." },
  { key: "expensive_calls", label: "Expensive Calls", description: "Best calls to sell. Priced expecting the underlying to move up more than it historically has." },
  { key: "expensive_puts", label: "Expensive Puts", description: "Best puts to sell. Priced expecting the underlying to move down more than it historically has." },
];

function formatExpiryDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const month = d.toLocaleString("en-US", { month: "long" });
  const day = d.getDate();
  const year = d.getFullYear();
  const suffix = day === 1 || day === 21 || day === 31 ? "st"
    : day === 2 || day === 22 ? "nd"
    : day === 3 || day === 23 ? "rd" : "th";
  return `${month} ${day}${suffix} ${year}`;
}

export default function ThetaPlaysPage() {
  const [results, setResults] = useState<ThetaPlaysResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("highest_premium");
  const [expiries, setExpiries] = useState<ThetaExpiry[]>([]);
  const [selectedExpiry, setSelectedExpiry] = useState<string>("");
  const [sortCol, setSortCol] = useState<string>("avg_premium");
  const [sortAsc, setSortAsc] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // Load available expiries on mount
  useEffect(() => {
    fetchThetaExpiries().then((exps) => {
      setExpiries(exps);
      if (exps.length > 0) {
        setSelectedExpiry(exps[0].expiry);
      } else {
        setLoading(false);
      }
    });
  }, []);

  // Load results when selected expiry changes
  useEffect(() => {
    if (!selectedExpiry) return;
    setLoading(true);
    setResults(null);
    fetchThetaPlays(selectedExpiry).then((res) => {
      setResults(res);
      setLoading(false);
    });
  }, [selectedExpiry]);

  const rows = results ? results[activeTab] : [];

  const sorted = [...rows].sort((a, b) => {
    const av = (a as Record<string, number>)[sortCol] ?? 0;
    const bv = (b as Record<string, number>)[sortCol] ?? 0;
    return sortAsc ? av - bv : bv - av;
  });

  const handleSort = (col: string) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{
        borderLeft: "3px solid #6c63ff",
        padding: "12px 16px",
        background: "#6c63ff08",
        borderRadius: "0 8px 8px 0",
        maxWidth: "70%",
      }}>
        <p style={{ margin: 0, fontSize: 14, color: "#aaa", lineHeight: 1.7 }}>
          Options with implied volatility (IV) higher than historical volatility (HV)
          are overpriced relative to actual moves.
          {" "}<strong style={{ color: "#ccc" }}>Sell these for theta decay.</strong>
        </p>
      </div>

      {/* Expiry selector */}
      <div style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}>
        <span style={{ fontSize: 12, color: "#888" }}>Expiry:</span>
        {expiries.length > 0 ? (
          <select
            value={selectedExpiry}
            onChange={(e) => setSelectedExpiry(e.target.value)}
            style={{
              padding: "5px 10px",
              borderRadius: 6,
              border: "1px solid #333",
              background: "#0f0f1a",
              color: "#e0e0e0",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              outline: "none",
            }}
          >
            {expiries.map((exp) => {
              const days = Math.round((new Date(exp.expiry + "T00:00:00").getTime() - Date.now()) / 86400000);
              return (
                <option key={exp.expiry} value={exp.expiry}>
                  {formatExpiryDate(exp.expiry)} ({days}d)
                </option>
              );
            })}
          </select>
        ) : (
          <span style={{ fontSize: 12, color: "#555" }}>No scans available</span>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: "#555", fontSize: 13 }}>
          Loading...
        </div>
      )}

      {/* Results */}
      {!loading && results && (
        <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16 }}>
          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  setSortCol(tab.key === "expensive_calls" ? "call_premium" : tab.key === "expensive_puts" ? "put_premium" : "avg_premium");
                  setSortAsc(false);
                  setShowAll(false);
                }}
                style={{
                  padding: "6px 14px",
                  borderRadius: 6,
                  border: `1px solid ${activeTab === tab.key ? "#6c63ff" : "#333"}`,
                  background: activeTab === tab.key ? "#6c63ff" : "transparent",
                  color: activeTab === tab.key ? "#fff" : "#888",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <p style={{ fontSize: 11, color: "#666", margin: "0 0 12px" }}>
            {TABS.find((t) => t.key === activeTab)?.description}
            {results.scanned_at && (
              <span style={{ color: "#555" }}> Last scan: {new Date(results.scanned_at).toLocaleString()}</span>
            )}
          </p>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      title={col.tooltip}
                      onClick={() => handleSort(col.key)}
                      style={{
                        padding: "8px 6px",
                        textAlign: col.align || "right",
                        color: sortCol === col.key ? "#6c63ff" : "#888",
                        cursor: "pointer",
                        borderBottom: "1px solid #2a2a4a",
                        fontWeight: 600,
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                        whiteSpace: "nowrap",
                        userSelect: "none",
                      }}
                    >
                      {col.key === "hv_20" && results?.hv_days ? `HV (${results.hv_days}d)` : col.label} {sortCol === col.key ? (sortAsc ? "\u25b2" : "\u25bc") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(showAll ? sorted : sorted.slice(0, 10)).map((row, i) => (
                  <tr key={row.ticker} style={{ background: i % 2 === 0 ? "transparent" : "#0f0f1a" }}>
                    {COLUMNS.map((col) => (
                      <td
                        key={col.key}
                        style={{
                          padding: "6px",
                          textAlign: col.align || "right",
                          borderBottom: "1px solid #1a1a2e",
                          color: col.color ? col.color(row) : "#ccc",
                          fontWeight: col.bold?.(row) ? 700 : 400,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {col.render(row)}
                      </td>
                    ))}
                  </tr>
                ))}
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={COLUMNS.length} style={{ padding: 20, textAlign: "center", color: "#555" }}>
                      No results for this category.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {sorted.length > 10 && (
              <div style={{ textAlign: "center", marginTop: 12 }}>
                <button
                  onClick={() => setShowAll(!showAll)}
                  style={{
                    background: "transparent",
                    border: "1px solid #333",
                    borderRadius: 6,
                    padding: "6px 20px",
                    color: "#6c63ff",
                    cursor: "pointer",
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {showAll ? "Show less" : `Show all ${sorted.length} results`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table column definitions
// ---------------------------------------------------------------------------

interface Column {
  key: string;
  label: string;
  tooltip: string;
  align?: "left" | "right" | "center";
  render: (row: ThetaPlayRow) => string;
  color?: (row: ThetaPlayRow) => string;
  bold?: (row: ThetaPlayRow) => boolean;
}

const COLUMNS: Column[] = [
  {
    key: "ticker",
    label: "Ticker",
    tooltip: "Stock symbol",
    align: "left",
    render: (r) => r.ticker,
    color: () => "#fff",
    bold: () => true,
  },
  {
    key: "spot",
    label: "Spot",
    tooltip: "Current stock price (last close from options data)",
    render: (r) => `$${r.spot.toFixed(0)}`,
  },
  {
    key: "call_strike",
    label: "Call / Put",
    tooltip: "ATM call and put strike prices nearest to spot",
    render: (r) => `$${r.call_strike.toFixed(0)} / $${r.put_strike.toFixed(0)}`,
    color: () => "#aaa",
  },
  {
    key: "pct_change_5d",
    label: "5d Change",
    tooltip: "Stock price change over the last 5 trading days",
    render: (r) => `${r.pct_change_5d >= 0 ? "+" : ""}${r.pct_change_5d.toFixed(1)}%`,
    color: (r) => r.pct_change_5d > 0 ? "#2ecc71" : r.pct_change_5d < 0 ? "#e74c3c" : "#888",
  },
  {
    key: "call_mid",
    label: "Call $",
    tooltip: "ATM call option mid price (average of bid and ask)",
    render: (r) => `$${r.call_mid.toFixed(2)}`,
  },
  {
    key: "put_mid",
    label: "Put $",
    tooltip: "ATM put option mid price (average of bid and ask)",
    render: (r) => `$${r.put_mid.toFixed(2)}`,
  },
  {
    key: "call_iv",
    label: "IV",
    tooltip: "Implied Volatility: the market's expected annualized move, derived from option prices",
    render: (r) => `${((r.call_iv + r.put_iv) / 2 * 100).toFixed(1)}%`,
  },
  {
    key: "hv_20",
    label: "HV",
    tooltip: "Historical Volatility: the actual annualized move over the last 20 trading days",
    render: (r) => `${(r.hv_20 * 100).toFixed(1)}%`,
  },
  {
    key: "avg_premium",
    label: "Premium",
    tooltip: "IV / HV ratio. Above 1.0 means options are priced for bigger moves than actually occurred. Higher = more overpriced = better to sell",
    render: (r) => `${r.avg_premium.toFixed(2)}x`,
    color: (r) => r.avg_premium >= 2.0 ? "#2ecc71" : r.avg_premium >= 1.5 ? "#a3d977" : r.avg_premium >= 1.0 ? "#ccc" : "#666",
    bold: (r) => r.avg_premium >= 1.5,
  },
  {
    key: "call_premium",
    label: "Call Prem",
    tooltip: "Call IV / HV. High values mean call options are especially overpriced (sell calls)",
    render: (r) => `${r.call_premium.toFixed(2)}x`,
    color: (r) => r.call_premium >= 1.5 ? "#2ecc71" : "#ccc",
  },
  {
    key: "put_premium",
    label: "Put Prem",
    tooltip: "Put IV / HV. High values mean put options are especially overpriced (sell puts)",
    render: (r) => `${r.put_premium.toFixed(2)}x`,
    color: (r) => r.put_premium >= 1.5 ? "#2ecc71" : "#ccc",
  },
  {
    key: "beta",
    label: "Beta",
    tooltip: "Correlation to SPY. 1.0 = moves with the market. >1 = more volatile. <1 = less volatile. Negative = inverse",
    render: (r) => r.beta.toFixed(2),
    color: () => "#aaa",
  },
];
