import { useState } from "react";
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
  const [settingsOpen, setSettingsOpen] = useState(false);

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

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Settings */}
      <div style={{ position: "relative" }}>
        {settingsOpen && (
          <div
            style={{
              position: "absolute",
              bottom: 44,
              left: 12,
              background: "#1a1a2e",
              border: "1px solid #2a2a4a",
              borderRadius: 8,
              padding: 12,
              width: 180,
              boxShadow: "0 -4px 16px rgba(0,0,0,0.4)",
              zIndex: 50,
            }}
          >
            <div style={{ fontSize: 11, color: "#888", marginBottom: 8, fontWeight: 600 }}>Settings</div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 12, color: "#ccc" }}>Theme</span>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  style={{
                    padding: "3px 8px",
                    borderRadius: 4,
                    border: "1px solid #6c63ff",
                    background: "#6c63ff22",
                    color: "#6c63ff",
                    cursor: "pointer",
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                  title="Current theme"
                >
                  Dark
                </button>
                <button
                  style={{
                    padding: "3px 8px",
                    borderRadius: 4,
                    border: "1px solid #333",
                    background: "transparent",
                    color: "#555",
                    cursor: "not-allowed",
                    fontSize: 10,
                    fontWeight: 600,
                  }}
                  title="Coming soon"
                >
                  Light
                </button>
              </div>
            </div>
          </div>
        )}
        <button
          onClick={() => setSettingsOpen(!settingsOpen)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 20px",
            border: "none",
            background: settingsOpen ? "#2a2a4a" : "transparent",
            color: settingsOpen ? "#fff" : "#666",
            cursor: "pointer",
            fontSize: 14,
            textAlign: "left",
            borderLeft: "3px solid transparent",
            width: "100%",
          }}
        >
          <span>⚙️</span>
          <span>Settings</span>
        </button>
      </div>
    </nav>
  );
}
