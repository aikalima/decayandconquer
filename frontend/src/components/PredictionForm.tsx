import { useState } from "react";
import type { PredictionParams } from "../types/prediction";

interface Props {
  onSubmit: (params: PredictionParams) => void;
  loading: boolean;
}

export default function PredictionForm({ onSubmit, loading }: Props) {
  const [ticker, setTicker] = useState("SPY");
  const [obsFrom, setObsFrom] = useState("2025-05-01");
  const [obsTo, setObsTo] = useState("2025-05-15");
  const [targetDate, setTargetDate] = useState("2025-09-01");
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [solver, setSolver] = useState<"brent" | "newton">("brent");
  const [kde, setKde] = useState(false);

  const isRange = obsFrom !== obsTo;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      ticker,
      obs_date_from: obsFrom,
      obs_date_to: obsTo,
      target_date: targetDate,
      risk_free_rate: riskFreeRate,
      solver,
      kernel_smooth: kde,
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "start" }}>
        <Field
          label="Ticker"
          hint="Stock symbol (e.g. SPY, AAPL, TSLA). Data is loaded from the local DuckDB database."
        >
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            style={inputStyle}
          />
        </Field>

        <Field
          label="Observation From"
          hint="Start of the observation window. The algorithm reads options data from this date forward."
        >
          <input
            type="date"
            value={obsFrom}
            onChange={(e) => setObsFrom(e.target.value)}
            style={inputStyle}
          />
        </Field>

        <Field
          label="Observation To"
          hint="End of the observation window. Set equal to 'From' for single-day. Set a range to average IV across multiple days for a smoother prediction."
        >
          <input
            type="date"
            value={obsTo}
            onChange={(e) => setObsTo(e.target.value)}
            style={inputStyle}
          />
        </Field>

        <Field
          label="Target Date"
          hint="The date to predict the price for. For backtesting, pick a past date to compare against the actual realized price."
        >
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            style={inputStyle}
          />
        </Field>

        <Field
          label="Risk-Free Rate"
          hint="Annualised Treasury rate (~0.04 for 2025)."
        >
          <input
            type="number"
            step="0.01"
            value={riskFreeRate}
            onChange={(e) => setRiskFreeRate(Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="IV Solver" hint="Brent is robust. Newton is faster but less stable.">
          <select
            value={solver}
            onChange={(e) => setSolver(e.target.value as "brent" | "newton")}
            style={inputStyle}
          >
            <option value="brent">Brent</option>
            <option value="newton">Newton</option>
          </select>
        </Field>

        <Field label="KDE Smooth" hint="Gaussian smoothing on the final PDF.">
          <label style={{ display: "flex", alignItems: "center", gap: 6, color: "#ccc", fontSize: 13, marginTop: 4 }}>
            <input
              type="checkbox"
              checked={kde}
              onChange={(e) => setKde(e.target.checked)}
            />
            Enable
          </label>
        </Field>

        <div style={{ display: "flex", alignItems: "end" }}>
          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "8px 24px",
              borderRadius: 6,
              border: "none",
              background: loading ? "#444" : "#6c63ff",
              color: "#fff",
              cursor: loading ? "wait" : "pointer",
              fontSize: 14,
              fontWeight: 600,
              height: 36,
              marginTop: 18,
            }}
          >
            {loading ? "Running..." : "Run Prediction"}
          </button>
        </div>
      </div>

      {isRange && (
        <div style={{ fontSize: 12, color: "#6c63ff", marginTop: -8 }}>
          IV Averaging mode: implied volatility will be averaged across trading days from {obsFrom} to {obsTo}
        </div>
      )}
    </form>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 200 }}>
      <label style={{ fontSize: 12, color: "#aaa", fontWeight: 600 }}>{label}</label>
      {children}
      {hint && (
        <span style={{ fontSize: 10, color: "#666", lineHeight: 1.4 }}>{hint}</span>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid #333",
  background: "#0f0f1a",
  color: "#e0e0e0",
  fontSize: 13,
  width: 140,
};
