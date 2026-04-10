import { useLocation, useNavigate } from "react-router-dom";

interface NavItem {
  label: string;
  path: string;
  disabled?: boolean;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Analyze", path: "/", icon: "📊" },
  { label: "Predictions", path: "/predictions", icon: "🔮" },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <nav
      style={{
        width: 220,
        background: "#16162a",
        borderRight: "1px solid #2a2a4a",
        padding: "20px 0",
        display: "flex",
        flexDirection: "column",
        gap: 4,
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
              padding: "10px 20px",
              border: "none",
              background: active ? "#2a2a4a" : "transparent",
              color: item.disabled ? "#555" : active ? "#fff" : "#aaa",
              cursor: item.disabled ? "not-allowed" : "pointer",
              fontSize: 14,
              textAlign: "left",
              borderLeft: active ? "3px solid #6c63ff" : "3px solid transparent",
              opacity: item.disabled ? 0.5 : 1,
            }}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
            {item.disabled && (
              <span
                style={{
                  fontSize: 10,
                  background: "#333",
                  padding: "2px 6px",
                  borderRadius: 4,
                  color: "#888",
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
