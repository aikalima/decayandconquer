import { useState } from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";
import ChatPanel from "../components/ChatPanel";

function getChatPref(): boolean {
  const v = localStorage.getItem("dacey_open");
  if (v === null) return true; // default open on first visit
  return v === "1";
}

export default function AppLayout() {
  const [chatOpen, setChatOpen] = useState(getChatPref);

  const toggleChat = () => {
    const next = !chatOpen;
    setChatOpen(next);
    localStorage.setItem("dacey_open", next ? "1" : "0");
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      <Header />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <main
          style={{
            flex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            padding: "30px 34px",
            scrollbarWidth: "none",
          }}
        >
          <Outlet />
        </main>

        {/* Chat toggle button */}
        <button
          onClick={toggleChat}
          style={{
            position: "fixed",
            right: chatOpen ? 400 : 0,
            top: "50%",
            transform: "translateY(-50%)",
            zIndex: 100,
            background: chatOpen ? "var(--surface-hover)" : "var(--brand)",
            border: chatOpen ? "1px solid var(--border)" : "none",
            borderRadius: "8px 0 0 8px",
            padding: "12px 6px",
            cursor: "pointer",
            fontSize: 18,
            color: chatOpen ? "var(--brand)" : "var(--text-on-accent)",
            transition: "right 0.2s ease",
            boxShadow: chatOpen ? "none" : "var(--shadow-soft)",
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
