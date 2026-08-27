import { useRef, useState, useCallback, useEffect, useMemo } from "react";
import { CATEGORY_COLORS } from "./categoryColors";

interface EventMarker {
  date: string;
  category: string;
}

interface Props {
  onObsRangeChange: (from: string, to: string) => void;
  onTargetDateChange: (date: string) => void;
  initialObsFrom?: string;
  initialObsTo?: string;
  initialTarget?: string;
  timelineStartDate?: string;
  timelineEndDate?: string;
  events?: EventMarker[];
  hoveredEventIndex?: number | null;
  onEventHover?: (index: number | null) => void;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DEFAULT_START_DATE = "2025-01-01";
const DEFAULT_END_DATE = "2026-12-31";
const TRACK_TOTAL_WIDTH = 2400;

function parseLocalDate(dateStr: string): Date {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86400000);
}

function clampDay(day: number, totalDays: number): number {
  return Math.max(0, Math.min(totalDays, day));
}

function dateToDayIndex(dateStr: string, startDate: Date, totalDays: number): number {
  return clampDay(daysBetween(startDate, parseLocalDate(dateStr)), totalDays);
}

function dayIndexToDateStr(day: number, startDate: Date): string {
  const d = new Date(startDate.getTime() + day * 86400000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

function formatShort(day: number, startDate: Date): string {
  const d = new Date(startDate.getTime() + day * 86400000);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function todayIndex(startDate: Date, totalDays: number): number {
  const now = new Date();
  return clampDay(Math.round((now.getTime() - startDate.getTime()) / 86400000), totalDays);
}

function isFuture(day: number, startDate: Date, totalDays: number): boolean {
  return day >= todayIndex(startDate, totalDays);
}

export default function TimelineSlider({
  onObsRangeChange,
  onTargetDateChange,
  initialObsFrom = "2025-11-01",
  initialObsTo = "2026-03-01",
  initialTarget,
  timelineStartDate = DEFAULT_START_DATE,
  timelineEndDate = DEFAULT_END_DATE,
  events = [],
  hoveredEventIndex,
  onEventHover,
}: Props) {
  const startDate = useMemo(() => parseLocalDate(timelineStartDate), [timelineStartDate]);
  const endDate = useMemo(() => parseLocalDate(timelineEndDate), [timelineEndDate]);
  const totalDays = useMemo(() => Math.max(1, daysBetween(startDate, endDate)), [startDate, endDate]);
  const toDayIndex = useCallback((dateStr: string) => dateToDayIndex(dateStr, startDate, totalDays), [startDate, totalDays]);
  const toDateStr = useCallback((day: number) => dayIndexToDateStr(clampDay(day, totalDays), startDate), [startDate, totalDays]);
  const initialRange = useMemo(() => {
    let from = toDayIndex(initialObsFrom);
    let to = toDayIndex(initialObsTo);
    if (to <= from) {
      to = Math.min(totalDays, from + 1);
      from = Math.max(0, to - 1);
    }
    return { from, to };
  }, [initialObsFrom, initialObsTo, toDayIndex, totalDays]);

  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(700);
  const [panOffset, setPanOffset] = useState(0); // px offset (negative = scrolled right)
  const [obsFrom, setObsFrom] = useState(() => initialRange.from);
  const [obsTo, setObsTo] = useState(() => initialRange.to);
  const [target, setTarget] = useState<number | null>(() =>
    initialTarget ? toDayIndex(initialTarget) : null
  );
  const [isPanning, setIsPanning] = useState(false);

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
    // Center to show both obs range and target dot
    const rightEdge = target !== null ? target : obsTo;
    const centerDay = (obsFrom + rightEdge) / 2;
    const centerX = (centerDay / totalDays) * TRACK_TOTAL_WIDTH;
    const frame = requestAnimationFrame(() => {
      setPanOffset(-(centerX - containerWidth / 2));
    });
    return () => cancelAnimationFrame(frame);
  }, [events]); // eslint-disable-line react-hooks/exhaustive-deps

  const dayToX = useCallback((d: number) => (d / totalDays) * TRACK_TOTAL_WIDTH + panOffset, [panOffset, totalDays]);
  const xToDay = useCallback(
    (x: number) => {
      const rawX = x - panOffset;
      return Math.round(Math.max(0, Math.min(totalDays, (rawX / TRACK_TOTAL_WIDTH) * totalDays)));
    },
    [panOffset, totalDays]
  );

  const emitObs = useCallback(
    (from: number, to: number) => {
      onObsRangeChange(toDateStr(from), toDateStr(to));
    },
    [onObsRangeChange, toDateStr]
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
      setIsPanning(true);
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
        const pxPerDay = TRACK_TOTAL_WIDTH / totalDays;
        const dayDelta = Math.round(dx / pxPerDay);
        const rangeSize = dragStart.current.toDay - dragStart.current.fromDay;
        let newFrom = dragStart.current.fromDay + dayDelta;
        let newTo = newFrom + rangeSize;
        if (newFrom < 0) { newFrom = 0; newTo = rangeSize; }
        if (newTo > totalDays) { newTo = totalDays; newFrom = newTo - rangeSize; }
        setObsFrom(newFrom);
        setObsTo(newTo);
        emitObs(newFrom, newTo);
      } else if (dragging.current === "target") {
        const newTarget = clampDay(Math.max(day, obsTo + 2), totalDays);
        if (newTarget <= obsTo) return;
        setTarget(newTarget);
        onTargetDateChange(toDateStr(newTarget));
      }
    },
    [obsFrom, obsTo, target, xToDay, emitObs, onTargetDateChange, containerWidth, totalDays, toDateStr]
  );

  const handlePointerUp = useCallback(() => {
    dragging.current = null;
    setIsPanning(false);
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (wasDragging.current) { wasDragging.current = false; return; }
      const rect = containerRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const day = xToDay(x);
      if (day > obsTo + 2) {
        setTarget(day);
        onTargetDateChange(toDateStr(day));
      }
    },
    [obsTo, xToDay, onTargetDateChange, toDateStr]
  );

  const fromX = dayToX(obsFrom);
  const toX = dayToX(obsTo);
  const targetX = target !== null ? dayToX(target) : null;
  const todayX = dayToX(todayIndex(startDate, totalDays));
  const targetIsFuture = target !== null && isFuture(target, startDate, totalDays);
  const targetColor = "var(--up)";

  // Month ticks
  const monthTicks: { x: number; label: string; isYear: boolean }[] = [];
  const monthCursor = new Date(startDate.getFullYear(), startDate.getMonth(), 1);
  while (monthCursor <= endDate) {
    const dayIdx = clampDay(daysBetween(startDate, monthCursor), totalDays);
    const m = monthCursor.getMonth();
    monthTicks.push({
      x: dayToX(dayIdx),
      label: m === 0 ? `${MONTHS[m]} ${monthCursor.getFullYear()}` : MONTHS[m],
      isYear: m === 0,
    });
    monthCursor.setMonth(monthCursor.getMonth() + 1);
  }

  return (
    <div style={{ position: "relative", padding: "14px 0 8px", userSelect: "none", minHeight: 128 }}>
      {/* Date labels */}
      <div style={{ position: "relative", height: 22, marginBottom: 4 }}>
        <div style={{ position: "absolute", left: 0, fontSize: 12, color: "var(--brand)", fontWeight: 750 }}>
          Observe: {formatShort(obsFrom, startDate)} to {formatShort(obsTo, startDate)}
        </div>
        <div style={{ position: "absolute", right: 0, fontSize: 12, color: target !== null ? targetColor : "var(--muted)", fontWeight: 750 }}>
          {target !== null
            ? `Target: ${formatShort(target, startDate)} ${targetIsFuture ? "(prediction)" : "(backtest)"}`
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
          cursor: isPanning ? "grabbing" : "grab",
          touchAction: "none",
          paddingTop: 20,
          paddingBottom: 4,
        }}
      >
        {/* Track bar */}
        <div
          ref={trackRef}
          style={{
            position: "relative",
            height: 10,
            background: "var(--input-bg)",
            border: "1px solid var(--border)",
            borderRadius: 4,
          }}
        >
          {/* Today line - full height */}
          <div style={{
            position: "absolute", left: todayX, top: -20, width: 2, height: 64,
            background: "var(--up)", opacity: 0.65, pointerEvents: "none", zIndex: 1,
            borderRadius: 1,
          }} />
          <div style={{
            position: "absolute", left: todayX + 5, top: -20, fontSize: 11,
            color: "var(--up)", fontWeight: 750, pointerEvents: "none", zIndex: 1,
          }}>
            Today
          </div>

          {/* Observation range fill */}
          <div
            data-tutorial="obs-range"
            onPointerDown={(e) => handlePointerDown("range", e)}
            style={{
              position: "absolute", left: fromX, width: Math.max(toX - fromX, 2), height: "100%",
              background: "var(--brand)", borderRadius: 4,
              cursor: "grab", zIndex: 2,
            }}
          />

          {/* Handles */}
          <Handle x={fromX} onPointerDown={(e) => handlePointerDown("left", e)} color="var(--brand)" />
          <Handle x={toX} onPointerDown={(e) => handlePointerDown("right", e)} color="var(--brand)" />
          {target !== null && targetX !== null && (
            <Handle x={targetX} onPointerDown={(e) => handlePointerDown("target", e)} color={targetColor} dataTutorial="target-dot" />
          )}

          {/* Event markers */}
          {events.map((evt, i) => {
            const evtX = dayToX(toDayIndex(evt.date));
            const color = CATEGORY_COLORS[evt.category] || "var(--muted)";
            const isHovered = hoveredEventIndex === i;
            return (
              <div key={`evt-${i}`} style={{ position: "absolute", left: evtX, top: -20, pointerEvents: "none", zIndex: 1 }}>
                {/* Vertical line */}
                <div style={{
                  width: 1,
                  height: 64,
                  background: color,
                  opacity: isHovered ? 0.8 : 0.3,
                  transition: "opacity 0.15s",
                  borderRadius: 1,
                }} />
                {/* Dot */}
                <div
                  onMouseEnter={(e) => { e.stopPropagation(); onEventHover?.(i); }}
                  onMouseLeave={(e) => { e.stopPropagation(); onEventHover?.(null); }}
                  style={{
                    position: "absolute",
                    top: -2,
                    left: isHovered ? -6 : -5,
                    width: isHovered ? 12 : 10,
                    height: isHovered ? 12 : 10,
                    borderRadius: "50%",
                    background: color,
                    border: "1.5px solid var(--input-bg)",
                    cursor: "pointer",
                    pointerEvents: "auto",
                    transition: "all 0.15s",
                    zIndex: 5,
                  }}
                />
              </div>
            );
          })}
        </div>

        {/* Month labels */}
        <div style={{ position: "relative", height: 22, marginTop: 6 }}>
          {monthTicks.map((t, i) => (
            <div key={i} style={{ position: "absolute", left: t.x, pointerEvents: "none" }}>
              <div style={{ width: 1, height: t.isYear ? 10 : 6, background: t.isYear ? "var(--muted)" : "var(--border-strong)" }} />
              <span style={{
                fontSize: t.isYear ? 11 : 10,
                color: t.isYear ? "var(--text-soft)" : "var(--muted)",
                fontWeight: t.isYear ? 750 : 500,
                position: "absolute", top: t.isYear ? 10 : 7, left: -8, whiteSpace: "nowrap",
              }}>
                {t.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Hint */}
      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6, textAlign: "center" }}>
        Drag to pan timeline. Indigo handles set the observation window. The green marker sets the target date.
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
        border: "2px solid var(--input-bg)",
        cursor: "ew-resize",
        zIndex: 3,
        touchAction: "none",
      }}
    />
  );
}
