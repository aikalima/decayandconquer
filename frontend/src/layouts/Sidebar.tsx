import { useLocation, useNavigate } from "react-router-dom";

interface NavItem {
  label: string;
  path: string;
  disabled?: boolean;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Backtest & Predict", path: "/", icon: "📊" },
  { label: "Theta Plays", path: "/theta-plays", icon: "🎯" },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav
      style={{
        width: 244,
        background: "var(--surface-subtle)",
        borderRight: "1px solid var(--border)",
        padding: "22px 0",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      {NAV_ITEMS.map((item) => {
        const active = item.path === "/"
          ? location.pathname === "/"
          : location.pathname.startsWith(item.path);
        return (
          <button
            key={item.path}
            onClick={() => !item.disabled && navigate(item.path)}
            disabled={item.disabled}
            title={item.disabled ? "Coming Soon" : item.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "12px 22px",
              border: "none",
              background: active ? "var(--surface-hover)" : "transparent",
              color: item.disabled ? "var(--muted-3)" : active ? "var(--text)" : "var(--muted)",
              cursor: item.disabled ? "not-allowed" : "pointer",
              fontSize: 15,
              fontWeight: active ? 750 : 600,
              textAlign: "left",
              borderLeft: active ? "3px solid var(--accent)" : "3px solid transparent",
              opacity: item.disabled ? 0.5 : 1,
            }}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
            {item.disabled && (
              <span
                style={{
                  fontSize: 10,
                  background: "var(--surface-elevated)",
                  padding: "2px 6px",
                  borderRadius: 4,
                  color: "var(--muted)",
                  marginLeft: "auto",
                }}
              >
                Soon
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
