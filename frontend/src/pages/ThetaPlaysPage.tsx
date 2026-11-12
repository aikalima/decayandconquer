import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { fetchAppDefaults, fetchThetaPlays, fetchThetaExpiries } from "../api/client";
import type { ThetaPlayRow, ThetaPlaysResponse, ThetaExpiry } from "../api/client";

type Tab = "highest_premium" | "expensive_calls" | "expensive_puts";

interface HeaderTooltipState {
  key: string;
  label: string;
  tooltip: string;
  left: number;
  top: number;
}

const TABS: { key: Tab; label: string; lead: string; description: string }[] = [
  { key: "highest_premium", label: "Highest Premium", lead: "Best candidates for iron condors.", description: "Options with the highest IV/HV ratio overall." },
  { key: "expensive_calls", label: "Expensive Calls", lead: "Best calls to sell.", description: "Priced expecting the underlying to move up more than it historically has." },
  { key: "expensive_puts", label: "Expensive Puts", lead: "Best puts to sell.", description: "Priced expecting the underlying to move down more than it historically has." },
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
  const [sortCol, setSortCol] = useState<string>("rank_score");
  const [sortAsc, setSortAsc] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showExplainer, setShowExplainer] = useState(false);
  const [headerTooltip, setHeaderTooltip] = useState<HeaderTooltipState | null>(null);
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
  const activeTabInfo = TABS.find((tab) => tab.key === activeTab) ?? TABS[0];

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

  const placeHeaderTooltip = (col: Column, left: number, top: number) => {
    const width = 320;
    const margin = 14;
    const maxLeft = typeof window === "undefined" ? left : window.innerWidth - width - margin;
    const maxTop = typeof window === "undefined" ? top : window.innerHeight - 150;
    setHeaderTooltip({
      key: col.key,
      label: col.label,
      tooltip: col.tooltip,
      left: Math.max(margin, Math.min(left, maxLeft)),
      top: Math.max(margin, Math.min(top, maxTop)),
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{
        borderLeft: "4px solid var(--brand)",
        padding: "22px 24px",
        background: "var(--brand-tint)",
        border: "1px solid var(--brand-border)",
        borderRadius: "0 8px 8px 0",
        maxWidth: "100%",
      }}>
        <h1 style={{ margin: "0 0 8px", fontSize: 30, lineHeight: 1.18, color: "var(--text)", letterSpacing: 0 }}>
          Find options premium that is priced too rich
        </h1>
        <p style={{ margin: 0, fontSize: 17, color: "var(--text-soft)", lineHeight: 1.6, maxWidth: 940 }}>
          Theta Plays ranks stocks where option-implied volatility is running hotter than recent realized moves,
          highlighting contracts that may be attractive to sell for premium decay.
          {" "}
          <span
            onClick={() => setShowExplainer(true)}
            style={{ color: "var(--brand)", cursor: "pointer", fontWeight: 800, marginLeft: 8 }}
          >
            Explain how it works
          </span>
        </p>
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18, boxShadow: "var(--shadow-soft)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 18, marginBottom: 16, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 420px", minWidth: 260 }}>
            <h2 style={{ margin: "0 0 5px", color: "var(--text)", fontSize: 20, lineHeight: 1.25, letterSpacing: 0 }}>
              Scan Results
            </h2>
            <p className="dashboard-caption" style={{ margin: 0 }}>
              Compare overpriced premium by expiration, then sort by IV/HV, call premium, put premium, beta, or recent move.
            </p>
          </div>

          <label style={{ display: "flex", flexDirection: "column", gap: 6, flex: "0 0 auto", minWidth: 230 }}>
            <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 800, textTransform: "uppercase", letterSpacing: 0 }}>
              Expiry
            </span>
            {expiries.length > 0 ? (
              <select
                value={selectedExpiry}
                onChange={(e) => {
                  setLoading(true);
                  setResults(null);
                  setSelectedExpiry(e.target.value);
                }}
                style={{
                  padding: "9px 11px",
                  borderRadius: 6,
                  border: "1px solid var(--border-strong)",
                  background: "var(--input-bg)",
                  color: "var(--text)",
                  fontSize: 14,
                  fontWeight: 750,
                  cursor: "pointer",
                  outline: "none",
                  minWidth: 230,
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
          </label>
        </div>

        {loading && (
          <div style={{ textAlign: "center", padding: "34px 20px", color: "var(--muted)", fontSize: 14, borderTop: "1px solid var(--border)" }}>
            Loading...
          </div>
        )}

        {!loading && !results && selectedExpiry && (
          <div style={{
            borderTop: "1px solid var(--border)",
            padding: "28px 4px 12px",
            color: "var(--muted)",
            fontSize: 14,
          }}>
            No theta scan found for {formatExpiryDate(selectedExpiry)} yet.
          </div>
        )}

        {!loading && results && (
          <>
            <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", borderTop: "1px solid var(--border)", paddingTop: 16 }}>
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => {
                    setActiveTab(tab.key);
                    setSortCol(tab.key === "expensive_calls" ? "call_rank_score" : tab.key === "expensive_puts" ? "put_rank_score" : "rank_score");
                    setSortAsc(false);
                    setShowAll(false);
                  }}
                  style={{
                    padding: "8px 14px",
                    borderRadius: 6,
                    border: `1px solid ${activeTab === tab.key ? "var(--brand-border)" : "var(--border)"}`,
                    background: activeTab === tab.key ? "var(--brand-tint)" : "transparent",
                    color: activeTab === tab.key ? "var(--brand-text)" : "var(--muted)",
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
              <strong style={{ color: "var(--brand-text)", fontSize: 15, fontWeight: 850 }}>
                {activeTabInfo.lead}
              </strong>
              {" "}
              {activeTabInfo.description}
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
                      onClick={() => handleSort(col.key)}
                      onMouseEnter={(e) => placeHeaderTooltip(col, e.clientX + 12, e.clientY + 14)}
                      onMouseMove={(e) => placeHeaderTooltip(col, e.clientX + 12, e.clientY + 14)}
                      onMouseLeave={() => setHeaderTooltip(null)}
                      onFocus={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        placeHeaderTooltip(col, rect.left, rect.bottom + 8);
                      }}
                      onBlur={() => setHeaderTooltip(null)}
                      tabIndex={0}
                      style={{
                        padding: "10px 8px",
                        textAlign: col.align || "right",
                        color: sortCol === col.key ? "var(--brand)" : "var(--muted)",
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
                    color: "var(--brand)",
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
          {headerTooltip && (
            <div
              role="tooltip"
              style={{
                position: "fixed",
                left: headerTooltip.left,
                top: headerTooltip.top,
                width: 320,
                maxWidth: "calc(100vw - 28px)",
                background: "var(--surface-elevated)",
                border: "1px solid var(--brand-border)",
                borderRadius: 8,
                padding: "10px 12px",
                color: "var(--text-soft)",
                fontSize: 12,
                lineHeight: 1.55,
                boxShadow: "var(--shadow)",
                zIndex: 1000,
                pointerEvents: "none",
                textTransform: "none",
                letterSpacing: 0,
              }}
            >
              <div style={{ color: "var(--brand-text)", fontSize: 13, fontWeight: 850, marginBottom: 4 }}>
                {headerTooltip.label}
              </div>
              <div>{headerTooltip.tooltip}</div>
            </div>
          )}
          </>
        )}
      </div>
      {showExplainer && <ThetaExplainerModal onClose={() => setShowExplainer(false)} />}
    </div>
  );
}

function ThetaExplainerModal({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "color-mix(in srgb, var(--page-bg) 72%, transparent)",
          zIndex: 10000,
        }}
      />
      <div
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "32px 36px",
          maxWidth: 660,
          width: "90vw",
          maxHeight: "80vh",
          overflowY: "auto",
          zIndex: 10001,
          boxShadow: "var(--shadow)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 22, color: "var(--text)" }}>How Theta Plays Works</h2>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              fontSize: 22,
              cursor: "pointer",
              padding: "0 4px",
            }}
          >
            X
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20, fontSize: 15, color: "var(--text-soft)", lineHeight: 1.7 }}>
          <ThetaSection title="The Idea">
            Option sellers want to collect premium when the market is pricing a bigger move than the stock is
            actually delivering. Theta Plays looks for that gap by comparing implied volatility from option prices
            against historical volatility from recent stock moves.
          </ThetaSection>

          <ThetaSection title="The Scan">
            For each configured monthly expiry, the scanner chooses a liquid ticker universe, finds near-the-money
            calls and puts, estimates each contract's implied volatility, and calculates the stock's recent realized
            volatility over a matching lookback window. The main score is IV divided by HV.
          </ThetaSection>

          <ThetaSection title="How To Read It">
            A premium ratio above 1.0 means options are priced for more movement than the stock recently showed.
            Higher ratios can be better candidates for selling premium, but they also deserve more scrutiny around
            earnings, news, liquidity, spreads, and position sizing.
          </ThetaSection>

          <ThetaSection title="The Tabs">
            Highest Premium ranks the best overall IV/HV gaps. Expensive Calls highlights names where calls look
            especially rich. Expensive Puts does the same for puts. The table also shows bid/ask quality, beta, and
            recent price change so you can avoid blindly chasing the biggest ratio.
          </ThetaSection>
        </div>

        <button
          onClick={onClose}
          style={{
            marginTop: 24,
            padding: "10px 28px",
            borderRadius: 8,
            border: "none",
            background: "var(--brand)",
            color: "var(--text-on-accent)",
            cursor: "pointer",
            fontSize: 15,
            fontWeight: 700,
            display: "block",
            marginLeft: "auto",
          }}
        >
          Got it
        </button>
      </div>
    </>
  );
}

function ThetaSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 style={{ margin: "0 0 8px", fontSize: 16, color: "var(--text)", fontWeight: 800 }}>{title}</h3>
      <div>{children}</div>
    </section>
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
    tooltip: "The underlying stock symbol. Use it to identify the candidate and cross-check earnings, news, liquidity, and position sizing before selling premium.",
    align: "left",
    render: (r) => r.ticker,
    color: () => "var(--text)",
    bold: () => true,
  },
  {
    key: "spot",
    label: "Spot",
    tooltip: "The underlying stock price from the option data snapshot. It anchors which strikes are near the money and keeps the premium ratios in market context.",
    render: (r) => `$${r.spot.toFixed(0)}`,
  },
  {
    key: "call_strike",
    label: "Call / Put",
    tooltip: "The near-the-money call and put strikes selected for the scan. Near-ATM contracts are usually liquid and give a cleaner read on market-implied volatility.",
    render: (r) => `$${r.call_strike.toFixed(0)} / $${r.put_strike.toFixed(0)}`,
    color: () => "var(--muted)",
  },
  {
    key: "pct_change_5d",
    label: "5d Change",
    tooltip: "The stock's price change over the last five trading days. Recent momentum can reveal whether rich premium is compensation for a fresh move rather than a clean theta opportunity.",
    render: (r) => `${r.pct_change_5d >= 0 ? "+" : ""}${r.pct_change_5d.toFixed(1)}%`,
    color: (r) => r.pct_change_5d > 0 ? "var(--up)" : r.pct_change_5d < 0 ? "var(--down)" : "var(--muted)",
  },
  {
    key: "call_mid",
    label: "Call $",
    tooltip: "The selected call's mid price, computed from bid and ask when available. It approximates tradable premium and helps you avoid names where the premium looks rich but the dollars are too small.",
    render: (r) => `$${r.call_mid.toFixed(2)}`,
  },
  {
    key: "put_mid",
    label: "Put $",
    tooltip: "The selected put's mid price, computed from bid and ask when available. It shows the put-side premium available and helps compare call-rich versus put-rich opportunities.",
    render: (r) => `$${r.put_mid.toFixed(2)}`,
  },
  {
    key: "call_iv",
    label: "IV",
    tooltip: "Average implied volatility from the selected call and put. IV is the market's priced annualized move; theta sellers generally prefer high IV when actual movement is lower.",
    render: (r) => `${((r.call_iv + r.put_iv) / 2 * 100).toFixed(1)}%`,
  },
  {
    key: "hv_20",
    label: "HV",
    tooltip: "Historical volatility over the configured lookback window. HV is the stock's realized movement baseline, used to judge whether option prices are rich or merely fair.",
    render: (r) => `${(r.hv_20 * 100).toFixed(1)}%`,
  },
  {
    key: "avg_premium",
    label: "Premium",
    tooltip: "The average IV/HV ratio across the selected call and put. Above 1.0 means options price a bigger move than recent history; rows are ranked by a quality-adjusted version of this signal.",
    render: (r) => `${r.avg_premium.toFixed(2)}x`,
    color: (r) => r.avg_premium >= 1.5 ? "var(--risk)" : r.avg_premium >= 1.0 ? "var(--text-soft)" : "var(--muted)",
    bold: (r) => r.avg_premium >= 1.5,
  },
  {
    key: "quality_score",
    label: "Quality",
    tooltip: "Quote and liquidity sanity score. It penalizes missing bid/ask quotes, wide spreads, low open interest, stale or synthetic prices, large IV skew, and parity gaps so stale-looking premium does not float to the top.",
    render: (r) => r.quality_score == null ? "n/a" : `${r.quality_score.toFixed(0)}`,
    color: (r) => (r.quality_score ?? 100) < 60 ? "var(--risk)" : "var(--muted)",
    bold: (r) => (r.quality_score ?? 100) < 60,
  },
  {
    key: "call_premium",
    label: "Call Prem",
    tooltip: "The call-side IV/HV ratio. High values mean calls look especially rich versus realized movement, useful when looking for covered calls, call spreads, or the call side of an iron condor.",
    render: (r) => `${r.call_premium.toFixed(2)}x`,
    color: (r) => r.call_premium >= 1.5 ? "var(--risk)" : "var(--text-soft)",
  },
  {
    key: "put_premium",
    label: "Put Prem",
    tooltip: "The put-side IV/HV ratio. High values mean puts look especially rich versus realized movement, useful when looking for cash-secured puts, put spreads, or the put side of an iron condor.",
    render: (r) => `${r.put_premium.toFixed(2)}x`,
    color: (r) => r.put_premium >= 1.5 ? "var(--risk)" : "var(--text-soft)",
  },
  {
    key: "beta",
    label: "Beta",
    tooltip: "The stock's recent sensitivity to SPY. Beta helps size risk: high-beta names can move harder with the market, so rich premium may come with larger portfolio drawdown risk.",
    render: (r) => r.beta.toFixed(2),
    color: () => "var(--muted)",
  },
];
