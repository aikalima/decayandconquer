import { useState, useEffect } from "react";
import { fetchAppDefaults, fetchThetaPlays, fetchThetaExpiries } from "../api/client";
import type { ThetaPlayRow, ThetaPlaysResponse, ThetaExpiry } from "../api/client";

type Tab = "highest_premium" | "expensive_calls" | "expensive_puts";

const TABS: { key: Tab; label: string; description: string }[] = [
  { key: "highest_premium", label: "Highest Premium", description: "Best candidates for iron condors. Options with the highest IV/HV ratio overall." },
  { key: "expensive_calls", label: "Expensive Calls", description: "Best calls to sell. Priced expecting the underlying to move up more than it historically has." },
  { key: "expensive_puts", label: "Expensive Puts", description: "Best puts to sell. Priced expecting the underlying to move down more than it historically has." },
];

function thetaExpiryOptions(configured: ThetaExpiry[], available: ThetaExpiry[]): ThetaExpiry[] {
  const availableByExpiry = new Map(available.map((exp) => [exp.expiry, exp]));
  const base = configured.length > 0 ? configured : available;
  return base.map((exp) => {
    const scanned = availableByExpiry.get(exp.expiry);
    return {
      ...scanned,
      ...exp,
      last_scanned: scanned?.last_scanned ?? exp.last_scanned ?? "",
      tickers_scanned: scanned?.tickers_scanned ?? exp.tickers_scanned ?? 0,
    };
  });
}

function numericSortValue(row: ThetaPlayRow, col: string): number {
  const value = row[col as keyof ThetaPlayRow];
  return typeof value === "number" ? value : 0;
}

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
  const [nowMs] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;

    Promise.all([fetchAppDefaults(), fetchThetaExpiries()]).then(([defaults, exps]) => {
      if (cancelled) return;
      const configured = defaults?.theta.expiries.map((exp) => ({
        expiry: exp.expiry,
        name: exp.name,
        days_forward: exp.days_forward,
        last_scanned: "",
        tickers_scanned: 0,
      })) ?? [];
      const options = thetaExpiryOptions(configured, exps);
      setExpiries(options);
      if (options.length > 0) {
        setSelectedExpiry(options[0].expiry);
      } else {
        setLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // Load results when selected expiry changes
  useEffect(() => {
    if (!selectedExpiry) return;
    fetchThetaPlays(selectedExpiry).then((res) => {
      setResults(res);
      setLoading(false);
    });
  }, [selectedExpiry]);

  const rows = results ? results[activeTab] : [];

  const sorted = [...rows].sort((a, b) => {
    const av = numericSortValue(a, sortCol);
    const bv = numericSortValue(b, sortCol);
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
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      {/* Header */}
      <div style={{
        borderLeft: "4px solid var(--accent)",
        padding: "16px 18px",
        background: "var(--accent-soft)",
        border: "1px solid var(--accent-border)",
        borderRadius: "0 8px 8px 0",
        maxWidth: "100%",
      }}>
        <p style={{ margin: 0, fontSize: 15, color: "var(--text-soft)", lineHeight: 1.7 }}>
          Options with implied volatility (IV) higher than historical volatility (HV)
          are overpriced relative to actual moves.
          {" "}<strong style={{ color: "var(--text)" }}>Sell these for theta decay.</strong>
        </p>
      </div>

      {/* Expiry selector */}
      <div style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "14px 18px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        boxShadow: "var(--shadow-soft)",
      }}>
        <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 750 }}>Expiry:</span>
        {expiries.length > 0 ? (
          <select
            value={selectedExpiry}
            onChange={(e) => {
              setLoading(true);
              setResults(null);
              setSelectedExpiry(e.target.value);
            }}
            style={{
              padding: "7px 10px",
              borderRadius: 6,
              border: "1px solid var(--border-strong)",
              background: "var(--input-bg)",
              color: "var(--text)",
              fontSize: 14,
              fontWeight: 750,
              cursor: "pointer",
              outline: "none",
            }}
          >
            {expiries.map((exp) => {
              const computedDays = Math.round((new Date(exp.expiry + "T00:00:00").getTime() - nowMs) / 86400000);
              const days = exp.days_forward ?? computedDays;
              return (
                <option key={exp.expiry} value={exp.expiry}>
                  {formatExpiryDate(exp.expiry)} ({days}d)
                </option>
              );
            })}
          </select>
        ) : (
          <span style={{ fontSize: 13, color: "var(--muted)" }}>No scans available</span>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: "var(--muted)", fontSize: 14 }}>
          Loading...
        </div>
      )}

      {!loading && !results && selectedExpiry && (
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 20,
          color: "var(--muted)",
          boxShadow: "var(--shadow-soft)",
        }}>
          No theta scan found for {formatExpiryDate(selectedExpiry)} yet.
        </div>
      )}

      {/* Results */}
      {!loading && results && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, boxShadow: "var(--shadow-soft)" }}>
          {/* Tabs */}
          <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
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
                  padding: "8px 14px",
                  borderRadius: 6,
                  border: `1px solid ${activeTab === tab.key ? "var(--accent)" : "var(--border)"}`,
                  background: activeTab === tab.key ? "var(--accent)" : "transparent",
                  color: activeTab === tab.key ? "var(--text-on-accent)" : "var(--muted)",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 750,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <p className="dashboard-caption" style={{ margin: "0 0 14px" }}>
            {TABS.find((t) => t.key === activeTab)?.description}
            {results.scanned_at && (
              <span style={{ color: "var(--muted-2)" }}> Last scan: {new Date(results.scanned_at).toLocaleString()}</span>
            )}
          </p>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr>
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      title={col.tooltip}
                      onClick={() => handleSort(col.key)}
                      style={{
                        padding: "10px 8px",
                        textAlign: col.align || "right",
                        color: sortCol === col.key ? "var(--accent)" : "var(--muted)",
                        cursor: "pointer",
                        borderBottom: "1px solid var(--border)",
                        fontWeight: 800,
                        fontSize: 11,
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
                  <tr key={row.ticker} style={{ background: i % 2 === 0 ? "transparent" : "var(--surface-subtle)" }}>
                    {COLUMNS.map((col) => (
                      <td
                        key={col.key}
                        style={{
                          padding: "9px 8px",
                          textAlign: col.align || "right",
                          borderBottom: "1px solid var(--border)",
                          color: col.color ? col.color(row) : "var(--text-soft)",
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
                    <td colSpan={COLUMNS.length} style={{ padding: 20, textAlign: "center", color: "var(--muted)" }}>
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
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "8px 20px",
                    color: "var(--accent)",
                    cursor: "pointer",
                    fontSize: 13,
                    fontWeight: 750,
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
    color: () => "var(--text)",
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
    color: () => "var(--muted)",
  },
  {
    key: "pct_change_5d",
    label: "5d Change",
    tooltip: "Stock price change over the last 5 trading days",
    render: (r) => `${r.pct_change_5d >= 0 ? "+" : ""}${r.pct_change_5d.toFixed(1)}%`,
    color: (r) => r.pct_change_5d > 0 ? "var(--success)" : r.pct_change_5d < 0 ? "var(--danger)" : "var(--muted)",
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
    color: (r) => r.avg_premium >= 2.0 ? "var(--success)" : r.avg_premium >= 1.5 ? "var(--success)" : r.avg_premium >= 1.0 ? "var(--text-soft)" : "var(--muted)",
    bold: (r) => r.avg_premium >= 1.5,
  },
  {
    key: "call_premium",
    label: "Call Prem",
    tooltip: "Call IV / HV. High values mean call options are especially overpriced (sell calls)",
    render: (r) => `${r.call_premium.toFixed(2)}x`,
    color: (r) => r.call_premium >= 1.5 ? "var(--success)" : "var(--text-soft)",
  },
  {
    key: "put_premium",
    label: "Put Prem",
    tooltip: "Put IV / HV. High values mean put options are especially overpriced (sell puts)",
    render: (r) => `${r.put_premium.toFixed(2)}x`,
    color: (r) => r.put_premium >= 1.5 ? "var(--success)" : "var(--text-soft)",
  },
  {
    key: "beta",
    label: "Beta",
    tooltip: "Correlation to SPY. 1.0 = moves with the market. >1 = more volatile. <1 = less volatile. Negative = inverse",
    render: (r) => r.beta.toFixed(2),
    color: () => "var(--muted)",
  },
];
