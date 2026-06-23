import { useTheme } from "../themeContext";

export default function Header() {
  const { theme, setTheme } = useTheme();

  return (
    <header
      style={{
        height: 64,
        background: "var(--surface)",
        color: "var(--text)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 28px",
        borderBottom: "1px solid var(--border)",
        boxShadow: "var(--shadow-soft)",
        zIndex: 5,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: 0 }}>
          Decay <span style={{ color: "var(--accent)" }}>And Conquer</span>
        </span>
        <span style={{ color: "var(--muted)", fontSize: 13, fontWeight: 600 }}>
          Options dashboard
        </span>
      </div>

      <div
        role="group"
        aria-label="Theme"
        style={{
          display: "flex",
          gap: 4,
          padding: 4,
          background: "var(--surface-subtle)",
          border: "1px solid var(--border)",
          borderRadius: 8,
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
              background: theme === mode ? "var(--accent)" : "transparent",
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
