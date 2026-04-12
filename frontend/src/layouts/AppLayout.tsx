import { useState } from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";
import Sidebar from "./Sidebar";
import ChatPanel from "../components/ChatPanel";

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(true);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "#0f0f1a",
        color: "#e0e0e0",
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      <Header />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <Sidebar />
        <main
          style={{
            flex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            padding: 24,
            scrollbarWidth: "none",
          }}
        >
          <Outlet />
        </main>

        {/* Chat toggle button */}
        <button
          onClick={() => setChatOpen(!chatOpen)}
          style={{
            position: "fixed",
            right: chatOpen ? 400 : 0,
            top: "50%",
            transform: "translateY(-50%)",
            zIndex: 100,
            background: chatOpen ? "#2a2a4a" : "#6c63ff",
            border: "none",
            borderRadius: "8px 0 0 8px",
            padding: "12px 6px",
            cursor: "pointer",
            fontSize: 18,
            color: "#fff",
            transition: "right 0.2s ease",
            boxShadow: chatOpen ? "none" : "-2px 0 8px rgba(108,99,255,0.3)",
          }}
          title={chatOpen ? "Close chat" : "Ask Dacey"}
        >
          {chatOpen ? "›" : "💬"}
        </button>

        {/* Chat panel */}
        {chatOpen && (
          <div style={{ width: 400, flexShrink: 0 }}>
            <ChatPanel />
          </div>
        )}
      </div>
    </div>
  );
}
