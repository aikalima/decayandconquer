import { useState } from "react";
import type { PredictionParams } from "../types/prediction";
import TimelineSlider from "./TimelineSlider";

interface Props {
  onSubmit: (params: PredictionParams) => void;
  loading: boolean;
  events?: { date: string; category: string }[];
  hoveredEventIndex?: number | null;
  onEventHover?: (index: number | null) => void;
}

function isTargetInFuture(targetDate: string): boolean {
  return targetDate >= new Date().toISOString().slice(0, 10);
}

function computeDefaults() {
  const now = new Date();
  // 2nd closest past month-start: go back 2 months from current month
  const endMonth = now.getMonth() - 1; // 1 month ago
  const endYear = now.getFullYear() + Math.floor(endMonth < 0 ? -1 : 0);
  const endM = ((endMonth % 12) + 12) % 12;
  const obsToDate = new Date(endYear, endM, 1);

  // 4 months before obsTo
  const startMonth = endM - 4;
  const startYear = endYear + Math.floor(startMonth < 0 ? -1 : 0);
  const startM = ((startMonth % 12) + 12) % 12;
  const obsFromDate = new Date(startYear, startM, 1);

  // Target: 2 months from today
  const targetMonth = now.getMonth() + 2;
  const targetYear = now.getFullYear() + Math.floor(targetMonth / 12);
  const targetM = targetMonth % 12;
  const targetDate = new Date(targetYear, targetM, now.getDate());

  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { obsFrom: fmt(obsFromDate), obsTo: fmt(obsToDate), target: fmt(targetDate) };
}

const DEFAULTS = computeDefaults();
export { DEFAULTS };

export default function PredictionForm({ onSubmit, loading, events, hoveredEventIndex, onEventHover }: Props) {
  const [ticker, setTicker] = useState("SPY");
  const [obsFrom, setObsFrom] = useState(DEFAULTS.obsFrom);
  const [obsTo, setObsTo] = useState(DEFAULTS.obsTo);
  const [targetDate, setTargetDate] = useState(DEFAULTS.target);
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [solver, setSolver] = useState<"brent" | "newton">("brent");
  const [kde, setKde] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const isValid = obsFrom && obsTo && targetDate && targetDate > obsTo;
  const isPrediction = isTargetInFuture(targetDate);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
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

  const buttonColor = isPrediction ? "#2ecc71" : "#6c63ff";
  const buttonLabel = isPrediction ? "Run Prediction" : "Run Backtest";

  return (
    <form
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: 12 }}
    >
      {/* Ticker card */}
      <div style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
      }}>
        <label style={{ fontSize: 12, color: "#888", fontWeight: 600 }}>Ticker</label>
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid #333",
            background: "#0f0f1a",
            color: "#e0e0e0",
            fontSize: 14,
            fontWeight: 600,
            width: 100,
            letterSpacing: 0.5,
            textAlign: "center",
          }}
        />
        <span style={{ fontSize: 12, color: "#555" }}>
          Enter any US stock symbol
        </span>
      </div>

      {/* Date range card */}
      <div data-tutorial="date-range" style={{
        background: "#1a1a2e",
        borderRadius: 8,
        padding: "16px 20px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 0,
      }}>

      {/* Timeline slider */}
      <TimelineSlider
        initialObsFrom={obsFrom}
        initialObsTo={obsTo}
        initialTarget={targetDate || undefined}
        onObsRangeChange={(from, to) => { setObsFrom(from); setObsTo(to); }}
        onTargetDateChange={(d) => setTargetDate(d)}
        events={events}
        hoveredEventIndex={hoveredEventIndex}
        onEventHover={onEventHover}
      />

      {/* Bottom row: Settings toggle + Run button */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        <button
          type="button"
          onClick={() => setShowSettings(!showSettings)}
          style={{
            background: "transparent",
            border: "1px solid #333",
            borderRadius: 6,
            padding: "5px 10px",
            color: showSettings ? "#6c63ff" : "#666",
            cursor: "pointer",
            fontSize: 12,
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          ⚙ Settings
        </button>

        <button
          type="submit"
          disabled={loading || !isValid}
          style={{
            padding: "8px 24px",
            borderRadius: 6,
            border: "none",
            background: loading || !isValid ? "#333" : buttonColor,
            color: loading || !isValid ? "#666" : "#fff",
            cursor: loading || !isValid ? "not-allowed" : "pointer",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {loading ? "Running..." : buttonLabel}
        </button>
      </div>

      {/* Collapsible settings panel */}
      {showSettings && (
        <div
          style={{
            display: "flex",
            gap: 16,
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid #2a2a4a",
            flexWrap: "wrap",
          }}
        >
          <SettingsField label="Risk-Free Rate" tooltip="The annualised US Treasury rate used in Black-Scholes pricing. 0.04 = 4%, which is typical for 2024-2025. This affects the discount factor applied to option prices when extracting the probability distribution.">
            <input
              type="number"
              step="0.01"
              value={riskFreeRate}
              onChange={(e) => setRiskFreeRate(Number(e.target.value))}
              style={settingsInputStyle}
            />
          </SettingsField>

          <SettingsField label="IV Solver" tooltip="The numerical method used to invert Black-Scholes and extract implied volatility from each option price. Brent's method is robust and reliable (recommended). Newton-Raphson is faster but can fail on edge cases with deep OTM options.">
            <select
              value={solver}
              onChange={(e) => setSolver(e.target.value as "brent" | "newton")}
              style={settingsInputStyle}
            >
              <option value="brent">Brent</option>
              <option value="newton">Newton</option>
            </select>
          </SettingsField>

          <SettingsField label="KDE Smooth" tooltip="Apply Gaussian Kernel Density Estimation to smooth the final probability distribution. Produces a cleaner curve but may slightly shift the peak. Useful when the raw distribution has noise from sparse option data.">
            <label style={{ display: "flex", alignItems: "center", gap: 6, color: "#ccc", fontSize: 12 }}>
              <input
                type="checkbox"
                checked={kde}
                onChange={(e) => setKde(e.target.checked)}
              />
              Enable
            </label>
          </SettingsField>
        </div>
      )}

      </div>{/* end date range card */}
    </form>
  );
}

function SettingsField({ label, tooltip, children }: { label: string; tooltip?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }} title={tooltip}>
      <label style={{ fontSize: 10, color: "#888", cursor: tooltip ? "help" : undefined, borderBottom: tooltip ? "1px dotted #444" : undefined, display: "inline", alignSelf: "flex-start" }}>{label}</label>
      {children}
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
  width: 100,
};

const settingsInputStyle: React.CSSProperties = {
  padding: "5px 8px",
  borderRadius: 6,
  border: "1px solid #333",
  background: "#0f0f1a",
  color: "#e0e0e0",
  fontSize: 12,
  width: 100,
};
