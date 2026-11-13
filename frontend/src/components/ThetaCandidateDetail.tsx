import { useEffect, useRef } from "react";
import type { ThetaPlayRow } from "../api/client";

type Category = "highest_premium" | "expensive_calls" | "expensive_puts";
const time = (value?: string | null) => !value ? "Unknown" : /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value} (daily close)` : new Date(value).toLocaleString();
const value = (n?: number | null, suffix = "") => n == null || !Number.isFinite(n) ? "Unknown" : `${n.toLocaleString()}${suffix}`;
const source = (name?: string) => name ? name.replaceAll("_", " ") : "Unknown / legacy scan";

export default function ThetaCandidateDetail({ row, category, onClose }: { row: ThetaPlayRow; category: Category; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => { element?.close(); previousFocus?.focus(); };
  }, []);
  const check = row.quality?.eligibility[category];
  const ranking = row.quality?.ranking?.[category];
  const ratio = category === "expensive_calls" ? row.call_premium : category === "expensive_puts" ? row.put_premium : row.avg_premium;
  const score = category === "expensive_calls" ? row.call_rank_score : category === "expensive_puts" ? row.put_rank_score : row.rank_score;
  return (
    <dialog ref={dialog} className="theta-detail" aria-labelledby="theta-detail-title" onCancel={onClose} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <header className="theta-detail-header">
        <div><h2 id="theta-detail-title">{row.ticker} <span>Candidate review</span></h2><p>Expiry {row.expiry} · Underlying ${value(row.spot)}</p></div>
        <button type="button" onClick={onClose} autoFocus>Close details</button>
      </header>
      <section>
        <h3>{check?.eligible ? "Passes research data checks" : "Excluded from the default ranking"}</h3>
        <p>Volatility richness <strong>{value(ratio, "x")}</strong> · Quality-adjusted score <strong>{value(score)}</strong></p>
        {ranking && <p>{value(ranking.raw_ratio, "x")} × {value(ranking.quality_multiplier)} input-quality multiplier = {value(ranking.calculated_score)}.
          {ranking.saved_score != null && <> Saved scan score: {value(ranking.saved_score)}. The lower score is used to preserve the original scan penalties.</>}</p>}
        <p>IV/HV compares option-implied volatility with recent realized volatility. It is not a dollar premium, a probability of profit, or a recommendation. Scores can only be reduced by data-quality checks; a zero score stays zero.</p>
        {check && !check.eligible && <ul>{check.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      </section>
      <section>
        <h3>Price provenance</h3>
        <dl className="theta-detail-facts">
          <div><dt>Scanned</dt><dd>{time(row.quality?.scanned_at)}</dd></div>
          <div><dt>Underlying observed</dt><dd>{time(row.quality?.underlying_at)}</dd></div>
          <div><dt>Underlying source</dt><dd>{source(row.spot_source)}</dd></div>
          <div><dt>HV window</dt><dd>{row.hv_start_date ?? "Unknown"} to {row.hv_end_date ?? "Unknown"}</dd></div>
          <div><dt>HV history</dt><dd>{value(row.hv_observations)} closes / {value(row.hv_days)} returns requested</dd></div>
          <div><dt>HV source</dt><dd>{source(row.hv_source)}</dd></div>
        </dl>
      </section>
      <section>
        <h3>Selected contracts</h3>
        <div className="theta-contracts">{(["call", "put"] as const).map((side) => {
          const leg = row.quality?.legs[side];
          return <div key={side}>
            <h4>{side === "call" ? "Call" : "Put"} · ${value(row[`${side}_strike`])} strike</h4>
            <dl>
              <dt>Reference price / share</dt><dd>${value(row[`${side}_mid`])}</dd>
              <dt>Price source</dt><dd>{source(leg?.price_source)}</dd>
              <dt>Price last updated</dt><dd>{time(leg?.price_at)}</dd>
              <dt>Bid / ask</dt><dd>{row[`${side}_bid`] > 0 && row[`${side}_ask`] > 0 ? `$${value(row[`${side}_bid`])} / $${value(row[`${side}_ask`])}` : "Unavailable"}</dd>
              <dt>Spread / midpoint</dt><dd>{value(leg?.spread_pct, "%")}</dd>
              <dt>Open interest / volume</dt><dd>{value(row[`${side}_open_interest`])} / {value(row[`${side}_volume`])}</dd>
              <dt>IV / IV source</dt><dd>{value(Math.round(row[`${side}_iv`] * 10000) / 100, "%")} / {source(row[`${side}_iv_source`])}</dd>
            </dl>
          </div>;
        })}</div>
        <p>Reference prices may be daily closes or last trades, not executable quotes. Bid/ask snapshots also need broker verification.</p>
      </section>
      <section>
        <h3>Limitations &amp; cautions</h3>
        <ul>{row.quality?.flags.filter((f) => !f.blocking).map((f) => <li key={f.code}>{f.message}</li>)}
          {row.quality_warnings && <li>{row.quality_warnings}</li>}
          <li>Dividend and earnings effects are not verified. Locally solved IV uses European pricing without dividends; a call/put difference alone is not proof of mispricing.</li>
          <li>Freshness uses a four-calendar-day limit, not a trading-session calendar. Passing these checks does not establish an executable trade or positive expected return.</li>
        </ul>
      </section>
    </dialog>
  );
}
