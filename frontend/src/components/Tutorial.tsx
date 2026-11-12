import { useState, useEffect } from "react";
import { setTutorialTrigger, STORAGE_KEY } from "./tutorialController";

interface Step {
  title: string;
  text: string;
  target: string;
  /** Element to anchor the tooltip to (defaults to target) */
  tooltipAnchor?: string;
  position: "top" | "bottom";
  animation?: "slide-range" | "slide-target";
}

const STEPS: Step[] = [
  {
    title: "1. Enter a Ticker",
    text: "Type any US stock symbol (SPY, AAPL, TSLA, NVDA). The system will look up its options data to build a price prediction.",
    target: '[data-tutorial="ticker-input"]',
    position: "bottom",
  },
  {
    title: "2. Set the Observation Window",
    text: "This indigo range defines which dates of options data to use. A wider range averages implied volatility across more days, producing a smoother and more stable prediction. Drag the handles to adjust.",
    target: '[data-tutorial="obs-range"]',
    tooltipAnchor: '[data-tutorial="date-range"]',
    position: "bottom",
    animation: "slide-range",
  },
  {
    title: "3. Set a Target Date",
    text: "Click or drag the green marker to set the date you want to predict the stock price for. If the target is in the past, you get a backtest (compares prediction vs actual). If it's in the future, you get a forward prediction.",
    target: '[data-tutorial="target-dot"]',
    tooltipAnchor: '[data-tutorial="date-range"]',
    position: "bottom",
    animation: "slide-target",
  },
  {
    title: "4. Run It",
    text: "Hit the button to run the prediction pipeline. It extracts the market's implied probability distribution from options prices, showing you the most likely price range and confidence intervals.",
    target: 'button[type="submit"]',
    position: "top",
  },
];

export default function Tutorial() {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [tooltipRect, setTooltipRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    setTutorialTrigger(() => {
      setStep(0);
      setVisible(true);
    });
    return () => setTutorialTrigger(null);
  }, []);

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return;
    const timer = setTimeout(() => setVisible(true), 800);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const currentStep = STEPS[step];
    const el = document.querySelector(currentStep.target);
    const frame = requestAnimationFrame(() => {
      if (!el) return;
      setTargetRect(el.getBoundingClientRect());
      // Tooltip anchors to a different element if specified
      const anchorEl = currentStep.tooltipAnchor
        ? document.querySelector(currentStep.tooltipAnchor)
        : el;
      setTooltipRect(anchorEl ? anchorEl.getBoundingClientRect() : el.getBoundingClientRect());
    });
    return () => cancelAnimationFrame(frame);
  }, [step, visible]);

  if (!visible) return null;

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, "true");
    setVisible(false);
  };

  const next = () => {
    if (isLast) {
      dismiss();
    } else {
      setStep(step + 1);
    }
  };

  const tooltipStyle: React.CSSProperties = {
    position: "fixed",
    zIndex: 10000,
    background: "var(--surface)",
    border: "2px solid var(--brand)",
    borderRadius: 8,
    padding: "16px 20px",
    maxWidth: 360,
    boxShadow: "var(--shadow)",
  };

  const anchorRect = tooltipRect || targetRect;
  if (anchorRect) {
    if (currentStep.position === "bottom") {
      tooltipStyle.top = anchorRect.bottom + 12;
      tooltipStyle.left = Math.max(16, anchorRect.left);
    } else if (currentStep.position === "top") {
      tooltipStyle.bottom = window.innerHeight - anchorRect.top + 12;
      tooltipStyle.right = 24;
    }
  } else {
    tooltipStyle.top = "50%";
    tooltipStyle.left = "50%";
    tooltipStyle.transform = "translate(-50%, -50%)";
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={dismiss}
        style={{
          position: "fixed",
          inset: 0,
          background: "color-mix(in srgb, var(--page-bg) 68%, transparent)",
          zIndex: 9998,
        }}
      />

      {/* Highlight ring around target */}
      {targetRect && (() => {
        const isTargetDot = currentStep.animation === "slide-target";
        const isObsRange = currentStep.animation === "slide-range";
        const pad = isTargetDot ? 8 : isObsRange ? 4 : 6;
        const radius = isTargetDot ? "50%" : isObsRange ? "10px" : "8px";
        const glowColor = isTargetDot ? "var(--up-tint)" : "var(--brand-tint)";
        const glowColorStrong = isTargetDot ? "var(--up)" : "var(--brand)";
        const borderColor = isTargetDot ? "var(--up)" : "var(--brand)";
        const animName = currentStep.animation ? "tutorial-pulse" : undefined;

        // If element is off-screen (e.g. panned timeline), don't show highlight
        const vw = window.innerWidth;
        const elLeft = targetRect.left - pad;
        const elRight = targetRect.right + pad;
        if (elRight < 0 || elLeft > vw) return null;

        return (
          <div
            style={{
              position: "fixed",
              left: targetRect.left - pad,
              top: targetRect.top - pad,
              width: targetRect.width + pad * 2,
              height: targetRect.height + pad * 2,
              border: `2px solid ${borderColor}`,
              borderRadius: radius,
              zIndex: 9999,
              pointerEvents: "none",
              boxShadow: `0 0 20px ${glowColor}`,
              transition: "all 0.3s ease",
              animation: animName ? `${animName} 1.5s ease-in-out infinite` : undefined,
              ["--glow" as string]: glowColor,
              ["--glow-strong" as string]: glowColorStrong,
            }}
          />
        );
      })()}

      {/* empty — animation handled by pulsating highlight ring */}

      {/* Tooltip */}
      <div style={tooltipStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 800, color: "var(--brand)" }}>
            {currentStep.title}
          </span>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            {step + 1} / {STEPS.length}
          </span>
        </div>

        <p style={{ fontSize: 14, color: "var(--text-soft)", lineHeight: 1.6, margin: "0 0 14px" }}>
          {currentStep.text}
        </p>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button
            onClick={dismiss}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              cursor: "pointer",
              fontSize: 13,
              padding: 0,
            }}
          >
            Skip tutorial
          </button>

          <button
            onClick={next}
            style={{
              padding: "6px 18px",
              borderRadius: 6,
              border: "none",
              background: "var(--brand)",
              color: "var(--text-on-accent)",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 750,
            }}
          >
            {isLast ? "Got it!" : "Next"}
          </button>
        </div>

        {/* Step dots */}
        <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 12 }}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: i === step ? "var(--brand)" : "var(--border-strong)",
                transition: "background 0.2s",
              }}
            />
          ))}
        </div>
      </div>

      {/* CSS animation */}
      <style>{`
        @keyframes tutorial-pulse {
          0%, 100% { box-shadow: 0 0 20px var(--glow); }
          50% { box-shadow: 0 0 40px var(--glow-strong), 0 0 60px var(--glow); }
        }
      `}</style>
    </>
  );
}
