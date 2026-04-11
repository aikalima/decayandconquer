import { useState } from "react";
import ProgressBar from "../components/ProgressBar";
import { fetchThetaPlaysStream } from "../api/client";
import type { ThetaPlayRow, ThetaPlaysResponse } from "../api/client";

type Tab = "highest_premium" | "expensive_calls" | "expensive_puts";

const TABS: { key: Tab; label: string; description: string }[] = [
  { key: "highest_premium", label: "Highest Premium", description: "Best candidates for iron condors. Options with the highest IV/HV ratio overall." },
  { key: "expensive_calls", label: "Expensive Calls", description: "Best calls to sell. Priced expecting the underlying to move up more than it historically has." },
  { key: "expensive_puts", label: "Expensive Puts", description: "Best puts to sell. Priced expecting the underlying to move down more than it historically has." },
];

const DTE_OPTIONS = [14, 30, 45, 60];

export default function ThetaPlaysPage() {
  const [results, setResults] = useState<ThetaPlaysResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("highest_premium");
  const [dte, setDte] = useState(30);
  const [sortCol, setSortCol] = useState<string>("avg_premium");
  const [sortAsc, setSortAsc] = useState(false);

  const handleScan = async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    setProgress(0);
    setStage("Starting scan...");

    try {
      const res = await fetchThetaPlaysStream("", dte, (event) => {
        if (event.stage) setStage(event.stage);
        setProgress(event.progress);
      });
      setResults(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  };

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
      <div style={{ maxWidth: "70%" }}>
        <p style={{ margin: 0, fontSize: 13, color: "#888", lineHeight: 1.6 }}>
          Scan the options market for overpriced premium. When implied volatility (IV) exceeds
          historical volatility (HV), options are priced for bigger moves than the stock has
          actually made. Sell these for theta decay.
        </p>
      </div>

      {/* Controls */}
      <div style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "#888" }}>Expiry in:</span>
          {DTE_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDte(d)}
              style={{
                padding: "4px 10px",
                borderRadius: 4,
                border: `1px solid ${dte === d ? "#6c63ff" : "#333"}`,
                background: dte === d ? "#6c63ff" : "transparent",
                color: dte === d ? "#fff" : "#888",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {d}d
            </button>
          ))}
        </div>

        <button
          onClick={handleScan}
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
          {loading ? "Scanning..." : "Scan Now"}
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

      {/* Results */}
      {results && (
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
            {" "}Expiry: {results.expiry}. Scanned {results.tickers_scanned} tickers in {results.scan_time_seconds}s.
            {results.tickers_failed.length > 0 && (
              <span style={{ color: "#e67e22" }}> {results.tickers_failed.length} failed: {results.tickers_failed.join(", ")}</span>
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
                      {col.label} {sortCol === col.key ? (sortAsc ? "\u25b2" : "\u25bc") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, i) => (
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
  align?: "left" | "right" | "center";
  render: (row: ThetaPlayRow) => string;
  color?: (row: ThetaPlayRow) => string;
  bold?: (row: ThetaPlayRow) => boolean;
}

const COLUMNS: Column[] = [
  {
    key: "ticker",
    label: "Ticker",
    align: "left",
    render: (r) => r.ticker,
    color: () => "#fff",
    bold: () => true,
  },
  {
    key: "spot",
    label: "Spot",
    render: (r) => `$${r.spot.toFixed(0)}`,
  },
  {
    key: "call_strike",
    label: "Call / Put",
    render: (r) => `$${r.call_strike.toFixed(0)} / $${r.put_strike.toFixed(0)}`,
    color: () => "#aaa",
  },
  {
    key: "pct_change_5d",
    label: "5d Change",
    render: (r) => `${r.pct_change_5d >= 0 ? "+" : ""}${r.pct_change_5d.toFixed(1)}%`,
    color: (r) => r.pct_change_5d > 0 ? "#2ecc71" : r.pct_change_5d < 0 ? "#e74c3c" : "#888",
  },
  {
    key: "call_mid",
    label: "Call $",
    render: (r) => `$${r.call_mid.toFixed(2)}`,
  },
  {
    key: "put_mid",
    label: "Put $",
    render: (r) => `$${r.put_mid.toFixed(2)}`,
  },
  {
    key: "call_iv",
    label: "IV",
    render: (r) => `${((r.call_iv + r.put_iv) / 2 * 100).toFixed(1)}%`,
  },
  {
    key: "hv_20",
    label: "HV",
    render: (r) => `${(r.hv_20 * 100).toFixed(1)}%`,
  },
  {
    key: "avg_premium",
    label: "Premium",
    render: (r) => `${r.avg_premium.toFixed(2)}x`,
    color: (r) => r.avg_premium >= 2.0 ? "#2ecc71" : r.avg_premium >= 1.5 ? "#a3d977" : r.avg_premium >= 1.0 ? "#ccc" : "#666",
    bold: (r) => r.avg_premium >= 1.5,
  },
  {
    key: "call_premium",
    label: "Call Prem",
    render: (r) => `${r.call_premium.toFixed(2)}x`,
    color: (r) => r.call_premium >= 1.5 ? "#2ecc71" : "#ccc",
  },
  {
    key: "put_premium",
    label: "Put Prem",
    render: (r) => `${r.put_premium.toFixed(2)}x`,
    color: (r) => r.put_premium >= 1.5 ? "#2ecc71" : "#ccc",
  },
  {
    key: "call_efficiency",
    label: "Efficiency",
    render: (r) => `${((r.call_efficiency + r.put_efficiency) / 2).toFixed(0)}%`,
    color: (r) => {
      const avg = (r.call_efficiency + r.put_efficiency) / 2;
      return avg >= 80 ? "#2ecc71" : avg >= 50 ? "#f1c40f" : "#e74c3c";
    },
  },
  {
    key: "beta",
    label: "Beta",
    render: (r) => r.beta.toFixed(2),
    color: () => "#aaa",
  },
];
