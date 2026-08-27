import { useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../themeContext";

const NAV_ITEMS = [
  {
    label: "Predictions",
    path: "/",
    caption: "Backtest & forecast",
  },
  {
    label: "Theta Plays",
    path: "/theta-plays",
    caption: "Premium scanners",
  },
];

export default function Header() {
  const { theme, setTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <header
      className="app-header"
      style={{
        background: "var(--surface)",
        color: "var(--text)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: "1px solid var(--border)",
        boxShadow: "var(--shadow-soft)",
        zIndex: 5,
        gap: 16,
      }}
    >
      <div className="app-header-brand" style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0, whiteSpace: "nowrap" }}>
          Decay <span style={{ color: "var(--brand)" }}>And Conquer</span>
        </span>
        <span className="app-header-tagline" style={{ color: "var(--muted)", fontSize: 13, fontWeight: 650, whiteSpace: "nowrap" }}>
          Options dashboard
        </span>
      </div>

      <nav
        aria-label="Primary"
        className="top-nav"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-start",
          gap: 8,
          flex: "0 1 auto",
        }}
      >
        {NAV_ITEMS.map((item) => {
          const active = item.path === "/"
            ? location.pathname === "/"
            : location.pathname.startsWith(item.path);
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => navigate(item.path)}
              aria-current={active ? "page" : undefined}
              style={{
                minHeight: 38,
                border: `1px solid ${active ? "var(--brand-border)" : "var(--border)"}`,
                borderRadius: 8,
                padding: "6px 12px",
                cursor: "pointer",
                background: active ? "var(--brand-tint)" : "var(--surface-subtle)",
                color: active ? "var(--brand-text)" : "var(--text-soft)",
                boxShadow: active ? "inset 0 -2px 0 var(--brand)" : "none",
                display: "flex",
                alignItems: "center",
                gap: 8,
                whiteSpace: "nowrap",
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 850, lineHeight: 1 }}>
                {item.label}
              </span>
              <span style={{ fontSize: 11, color: active ? "var(--brand-text)" : "var(--muted)", fontWeight: 750, lineHeight: 1 }}>
                {item.caption}
              </span>
            </button>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <div
        role="group"
        aria-label="Theme"
        className="theme-toggle"
        style={{
          display: "flex",
          gap: 4,
          padding: 4,
          background: "var(--surface-subtle)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          flexShrink: 0,
        }}
      >
        {(["dark", "light"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setTheme(mode)}
            aria-pressed={theme === mode}
            style={{
              border: "none",
              borderRadius: 6,
              padding: "6px 12px",
              cursor: "pointer",
              background: theme === mode ? "var(--brand)" : "transparent",
              color: theme === mode ? "var(--text-on-accent)" : "var(--muted)",
              fontSize: 13,
              fontWeight: 750,
            }}
          >
            {mode === "dark" ? "Dark" : "Light"}
          </button>
        ))}
      </div>
    </header>
  );
}
