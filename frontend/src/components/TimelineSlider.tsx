import { useRef, useState, useCallback, useEffect } from "react";

interface Props {
  onObsRangeChange: (from: string, to: string) => void;
  onTargetDateChange: (date: string) => void;
  initialObsFrom?: string;
  initialObsTo?: string;
  initialTarget?: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const START_DATE = new Date(2025, 0, 1);
const END_DATE = new Date(2026, 11, 31);
const TOTAL_DAYS = Math.round((END_DATE.getTime() - START_DATE.getTime()) / 86400000);
const TRACK_TOTAL_WIDTH = 2400;

function dateToDayIndex(dateStr: string): number {
  const d = new Date(dateStr + "T00:00:00");
  return Math.round((d.getTime() - START_DATE.getTime()) / 86400000);
}

function dayIndexToDateStr(day: number): string {
  const d = new Date(START_DATE.getTime() + day * 86400000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function formatShort(day: number): string {
  const d = new Date(START_DATE.getTime() + day * 86400000);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function todayIndex(): number {
  const now = new Date();
  return Math.round((now.getTime() - START_DATE.getTime()) / 86400000);
}

function isFuture(day: number): boolean {
  return day >= todayIndex();
}

export default function TimelineSlider({
  onObsRangeChange,
  onTargetDateChange,
  initialObsFrom = "2025-11-01",
  initialObsTo = "2026-03-01",
  initialTarget,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(700);
  const [panOffset, setPanOffset] = useState(0); // px offset (negative = scrolled right)
  const [obsFrom, setObsFrom] = useState(() => dateToDayIndex(initialObsFrom));
  const [obsTo, setObsTo] = useState(() => dateToDayIndex(initialObsTo));
  const [target, setTarget] = useState<number | null>(() =>
    initialTarget ? dateToDayIndex(initialTarget) : null
  );

  const dragging = useRef<"left" | "right" | "range" | "target" | "pan" | null>(null);
  const dragStart = useRef({ x: 0, fromDay: 0, toDay: 0, panOffset: 0 });
  const wasDragging = useRef(false);

  // Measure container and set initial pan to center the obs range
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.getBoundingClientRect().width;
      setContainerWidth(w);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    // Center on obs range on mount
    const centerDay = (obsFrom + obsTo) / 2;
    const centerX = (centerDay / TOTAL_DAYS) * TRACK_TOTAL_WIDTH;
    setPanOffset(-(centerX - containerWidth / 2));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dayToX = useCallback((d: number) => (d / TOTAL_DAYS) * TRACK_TOTAL_WIDTH + panOffset, [panOffset]);
  const xToDay = useCallback(
    (x: number) => {
      const rawX = x - panOffset;
      return Math.round(Math.max(0, Math.min(TOTAL_DAYS, (rawX / TRACK_TOTAL_WIDTH) * TOTAL_DAYS)));
    },
    [panOffset]
  );

  const emitObs = useCallback(
    (from: number, to: number) => {
      onObsRangeChange(dayIndexToDateStr(from), dayIndexToDateStr(to));
    },
    [onObsRangeChange]
  );

  const handlePointerDown = useCallback(
    (type: "left" | "right" | "range" | "target", e: React.PointerEvent) => {
      e.stopPropagation();
      e.preventDefault();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      dragging.current = type;
      wasDragging.current = false;
      dragStart.current = { x: e.clientX, fromDay: obsFrom, toDay: obsTo, panOffset };
    },
    [obsFrom, obsTo, panOffset]
  );

  const handleContainerPointerDown = useCallback(
    (e: React.PointerEvent) => {
      // Only start pan if clicking on empty track area (not on a handle or range)
      if (dragging.current) return;
      dragging.current = "pan";
      wasDragging.current = false;
      dragStart.current = { x: e.clientX, fromDay: obsFrom, toDay: obsTo, panOffset };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [obsFrom, obsTo, panOffset]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current) return;
      wasDragging.current = true;

      if (dragging.current === "pan") {
        const dx = e.clientX - dragStart.current.x;
        const newOffset = dragStart.current.panOffset + dx;
        // Clamp so we don't pan past the edges
        const minOffset = -(TRACK_TOTAL_WIDTH - containerWidth);
        const maxOffset = 0;
        setPanOffset(Math.max(minOffset, Math.min(maxOffset, newOffset)));
        return;
      }

      const rect = containerRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const day = xToDay(x);

      if (dragging.current === "left") {
        const newFrom = Math.min(day, obsTo - 1);
        setObsFrom(newFrom);
        emitObs(newFrom, obsTo);
      } else if (dragging.current === "right") {
        const newTo = Math.max(day, obsFrom + 1);
        setObsTo(newTo);
        if (target !== null && newTo >= target) setTarget(null);
        emitObs(obsFrom, newTo);
      } else if (dragging.current === "range") {
        const dx = e.clientX - dragStart.current.x;
        const pxPerDay = TRACK_TOTAL_WIDTH / TOTAL_DAYS;
        const dayDelta = Math.round(dx / pxPerDay);
        const rangeSize = dragStart.current.toDay - dragStart.current.fromDay;
        let newFrom = dragStart.current.fromDay + dayDelta;
        let newTo = newFrom + rangeSize;
        if (newFrom < 0) { newFrom = 0; newTo = rangeSize; }
        if (newTo > TOTAL_DAYS) { newTo = TOTAL_DAYS; newFrom = newTo - rangeSize; }
        setObsFrom(newFrom);
        setObsTo(newTo);
        emitObs(newFrom, newTo);
      } else if (dragging.current === "target") {
        const newTarget = Math.max(day, obsTo + 2);
        setTarget(newTarget);
        onTargetDateChange(dayIndexToDateStr(newTarget));
      }
    },
    [obsFrom, obsTo, target, xToDay, emitObs, onTargetDateChange, containerWidth]
  );

  const handlePointerUp = useCallback(() => {
    dragging.current = null;
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (wasDragging.current) { wasDragging.current = false; return; }
      const rect = containerRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const day = xToDay(x);
      if (day > obsTo + 2) {
        setTarget(day);
        onTargetDateChange(dayIndexToDateStr(day));
      }
    },
    [obsTo, xToDay, onTargetDateChange]
  );

  const fromX = dayToX(obsFrom);
  const toX = dayToX(obsTo);
  const targetX = target !== null ? dayToX(target) : null;
  const todayX = dayToX(todayIndex());
  const targetIsFuture = target !== null && isFuture(target);
  const targetColor = targetIsFuture ? "#2ecc71" : "#e67e22";

  // Month ticks
  const monthTicks: { x: number; label: string; isYear: boolean }[] = [];
  for (let year = 2025; year <= 2026; year++) {
    for (let m = 0; m < 12; m++) {
      const dayIdx = dateToDayIndex(`${year}-${String(m + 1).padStart(2, "0")}-01`);
      monthTicks.push({
        x: dayToX(dayIdx),
        label: m === 0 ? `${MONTHS[m]} ${year}` : MONTHS[m],
        isYear: m === 0,
      });
    }
  }

  return (
    <div style={{ position: "relative", padding: "28px 0 8px", userSelect: "none", minHeight: 110 }}>
      {/* Date labels */}
      <div style={{ position: "relative", height: 18, marginBottom: 4 }}>
        <div style={{ position: "absolute", left: 0, fontSize: 10, color: "#6c63ff", fontWeight: 600 }}>
          Observe: {formatShort(obsFrom)} to {formatShort(obsTo)}
        </div>
        <div style={{ position: "absolute", right: 0, fontSize: 10, color: target !== null ? targetColor : "#555", fontWeight: 600 }}>
          {target !== null
            ? `Target: ${formatShort(target)} ${targetIsFuture ? "(prediction)" : "(backtest)"}`
            : "Click right of range to set target date"
          }
        </div>
      </div>

      {/* Track container (clips overflow, no scrollbar) */}
      <div
        ref={containerRef}
        onClick={handleClick}
        onPointerDown={handleContainerPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        style={{
          position: "relative",
          overflow: "hidden",
          cursor: dragging.current === "pan" ? "grabbing" : "grab",
          touchAction: "none",
          paddingTop: 12,
          paddingBottom: 4,
        }}
      >
        {/* Track bar */}
        <div
          ref={trackRef}
          style={{
            position: "relative",
            height: 8,
            background: "#0f0f1a",
            borderRadius: 4,
          }}
        >
          {/* Today line - full height */}
          <div style={{
            position: "absolute", left: todayX, top: -12, width: 2, height: 56,
            background: "#2ecc71", opacity: 0.6, pointerEvents: "none", zIndex: 1,
            borderRadius: 1,
          }} />
          <div style={{
            position: "absolute", left: todayX + 5, top: -10, fontSize: 9,
            color: "#2ecc71", fontWeight: 600, pointerEvents: "none", zIndex: 1,
          }}>
            Today
          </div>

          {/* Observation range fill */}
          <div
            data-tutorial="obs-range"
            onPointerDown={(e) => handlePointerDown("range", e)}
            style={{
              position: "absolute", left: fromX, width: Math.max(toX - fromX, 2), height: "100%",
              background: "linear-gradient(90deg, #6c63ff, #4a90d9)", borderRadius: 4,
              cursor: "grab", zIndex: 2,
            }}
          />

          {/* Handles */}
          <Handle x={fromX} onPointerDown={(e) => handlePointerDown("left", e)} color="#6c63ff" />
          <Handle x={toX} onPointerDown={(e) => handlePointerDown("right", e)} color="#6c63ff" />
          {target !== null && targetX !== null && (
            <Handle x={targetX} onPointerDown={(e) => handlePointerDown("target", e)} color={targetColor} dataTutorial="target-dot" />
          )}
        </div>

        {/* Month labels */}
        <div style={{ position: "relative", height: 22, marginTop: 6 }}>
          {monthTicks.map((t, i) => (
            <div key={i} style={{ position: "absolute", left: t.x, pointerEvents: "none" }}>
              <div style={{ width: 1, height: t.isYear ? 10 : 6, background: t.isYear ? "#666" : "#444" }} />
              <span style={{
                fontSize: t.isYear ? 10 : 9,
                color: t.isYear ? "#aaa" : "#666",
                fontWeight: t.isYear ? 600 : 400,
                position: "absolute", top: t.isYear ? 10 : 7, left: -8, whiteSpace: "nowrap",
              }}>
                {t.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Hint */}
      <div style={{ fontSize: 10, color: "#555", marginTop: 4, textAlign: "center" }}>
        Drag to pan timeline. Purple handles for observation window. Orange/green handle or click for target date.
      </div>
    </div>
  );
}

function Handle({
  x,
  onPointerDown,
  color,
  dataTutorial,
}: {
  x: number;
  onPointerDown: (e: React.PointerEvent) => void;
  color: string;
  dataTutorial?: string;
}) {
  return (
    <div
      data-tutorial={dataTutorial}
      onPointerDown={onPointerDown}
      style={{
        position: "absolute",
        left: x - 7,
        top: -4,
        width: 16,
        height: 16,
        borderRadius: "50%",
        background: color,
        border: "2px solid #0f0f1a",
        cursor: "ew-resize",
        zIndex: 3,
        touchAction: "none",
      }}
    />
  );
}
