import { useEffect, useState } from "react";

interface Health {
  status: string;
  options: { rows: number; first_date: string | null; latest_date: string | null; age_calendar_days: number | null; unverified_weekday_gaps: string[] } | null;
  theta_scans: { expiry: string; last_scanned: string | null; age_hours: number | null; expired: boolean }[];
  warnings: string[];
  coverage_basis: string;
}

export default function DataHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_BASE || ""}/data-health`, { signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        setHealth(await response.json());
        setFailed(false);
      } catch {
        if (!controller.signal.aborted) setFailed(true);
      }
    }
    void refresh();
    const interval = setInterval(refresh, 60000);
    return () => { controller.abort(); clearInterval(interval); };
  }, []);
  const unavailable = failed || health?.status === "unavailable";
  return (
    <details className="data-health">
      <summary>
        <strong>Data health</strong>
        <span>{unavailable ? "Service unavailable" : health?.options?.latest_date
          ? `Options through ${health.options.latest_date} · ${health.status === "stale" ? "Stale" : "Recent"}`
          : health ? "No options data" : "Checking data..."}</span>
      </summary>
      <div className="data-health-details" role="status">
        {unavailable && <p>Cannot check current data health. The service may be offline or refreshing.</p>}
        {!unavailable && health && <>
          <p>{health.options?.rows.toLocaleString() ?? 0} options rows · {health.options?.first_date ?? "No start date"} to {health.options?.latest_date ?? "No end date"}. Freshness is measured in calendar days, not trading sessions.</p>
          {health.warnings.map(warning => <p key={warning}>{warning}</p>)}
          {!!health.options?.unverified_weekday_gaps.length && <p>{health.options.unverified_weekday_gaps.length} unclassified weekday gaps: {health.options.unverified_weekday_gaps.join(", ")}. {health.coverage_basis}</p>}
          <p>Stock prices: actual daily closes matched to each prediction date. Any options-derived estimates are flagged in the result. Intraday quotes are not used.</p>
          <p>Refresh job status: not available. Scan time does not prove that underlying data was refreshed.</p>
          <ul>{health.theta_scans.map(scan => <li key={scan.expiry}>{scan.expiry}: {scan.last_scanned ? `scanned ${scan.age_hours} hours ago` : "scan time unknown"}{scan.expired ? " (expired)" : ""}</li>)}</ul>
          {!health.theta_scans.length && <p>No scan metadata available.</p>}
        </>}
      </div>
    </details>
  );
}
