import { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";
import { sendChatMessage } from "../api/client";
import type { ChatMessage, ToolResult } from "../api/client";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  toolResults?: ToolResult[];
  loading?: boolean;
}

const markdownStyles = `
.chat-markdown p { margin: 4px 0; font-size: 11px; }
.chat-markdown ul, .chat-markdown ol { margin: 4px 0; padding-left: 16px; }
.chat-markdown li { margin: 2px 0; font-size: 11px; }
.chat-markdown strong { color: #fff; }
.chat-markdown code { background: #0f0f1a; padding: 1px 4px; border-radius: 3px; font-size: 10px; color: #a882ff; }
.chat-markdown pre { background: #0f0f1a; padding: 6px 8px; border-radius: 6px; overflow-x: auto; margin: 6px 0; }
.chat-markdown pre code { padding: 0; background: none; }
.chat-markdown h1, .chat-markdown h2, .chat-markdown h3 { margin: 8px 0 4px; font-size: 12px; color: #ccc; font-weight: 700; }
.chat-markdown h4, .chat-markdown h5 { margin: 6px 0 3px; font-size: 11px; color: #aaa; font-weight: 600; }
.chat-markdown table { border-collapse: collapse; margin: 6px 0; width: 100%; display: block; overflow-x: auto; font-size: 10px; }
.chat-markdown th, .chat-markdown td { border: 1px solid #2a2a4a; padding: 2px 6px; text-align: left; white-space: nowrap; }
.chat-markdown th { background: #0f0f1a; color: #888; font-weight: 600; }
.chat-markdown td { color: #ccc; }
.chat-markdown blockquote { border-left: 3px solid #6c63ff; margin: 6px 0; padding-left: 10px; color: #999; font-size: 11px; }
.chat-markdown a { color: #6c63ff; }
.chat-markdown hr { border: none; border-top: 1px solid #2a2a4a; margin: 8px 0; }
`;

export default function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    const userMsg: DisplayMessage = { role: "user", content: text };
    const loadingMsg: DisplayMessage = { role: "assistant", content: "", loading: true };
    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setLoading(true);

    try {
      const history: ChatMessage[] = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user" as const, content: text },
      ];

      const result = await sendChatMessage(history, "anthropic");

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: result.response,
          toolResults: result.tool_results,
        };
        return updated;
      });
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
        };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#12122a",
        borderLeft: "1px solid #2a2a4a",
      }}
    >
      <style>{markdownStyles}</style>

      {/* Header */}
      <div style={{
        padding: "10px 14px",
        borderBottom: "1px solid #2a2a4a",
        fontSize: 13,
        fontWeight: 600,
        color: "#888",
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}>
        <span>🧠</span> Ask Dacey
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          scrollbarWidth: "none",
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "#555", fontSize: 11, padding: "12px 0" }}>
            <p style={{ margin: "0 0 8px", color: "#666" }}>
              Ask about stocks, options, or theta plays:
            </p>
            {[
              "Which has better odds of a 10% gain by June: NVDA or AMD?",
              "What are the chances MSFT hits $400 by June 1st?",
              "Compare the downside risk of AAPL, TSLA, and META over the next 30 days",
              "What are the top theta plays right now?",
              "What options strategy do you recommend for AMZN?",
              "I spent $1,000 on MSTR put options on May 5th 2025, $170 strike, expiring Aug 15th 2025. Did I profit?",
            ].map((q) => (
              <button
                key={q}
                onClick={() => setInput(q)}
                style={{
                  display: "block",
                  width: "100%",
                  background: "#1a1a2e",
                  border: "1px solid #2a2a4a",
                  borderRadius: 5,
                  padding: "6px 10px",
                  color: "#777",
                  cursor: "pointer",
                  fontSize: 10,
                  textAlign: "left",
                  marginBottom: 4,
                }}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div
        style={{
          display: "flex",
          gap: 6,
          padding: "8px 12px 10px",
          borderTop: "1px solid #2a2a4a",
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Pricing, predictions, strategies..."
          disabled={loading}
          style={{
            flex: 1,
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid #333",
            background: "#0f0f1a",
            color: "#e0e0e0",
            fontSize: 12,
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          style={{
            padding: "8px 12px",
            borderRadius: 6,
            border: "none",
            background: loading ? "#333" : "#6c63ff",
            color: "#fff",
            cursor: loading ? "wait" : "pointer",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}

function fixBullets(text: string): string {
  // Convert "• " bullet characters to proper markdown "- " list items
  // Also ensure a blank line before the first bullet in a group
  return text.replace(/^(•\s)/gm, "- ").replace(/([^\n])\n(- )/g, "$1\n\n$2");
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";

  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div
        className={isUser ? undefined : "chat-markdown"}
        style={{
          maxWidth: "92%",
          padding: "6px 10px",
          borderRadius: 8,
          background: isUser ? "#6c63ff" : "#1a1a2e",
          color: isUser ? "#fff" : "#ddd",
          fontSize: 11,
          lineHeight: 1.6,
        }}
      >
        {message.loading ? (
          <span style={{ color: "#888" }}>Thinking...</span>
        ) : isUser ? (
          message.content
        ) : (
          <Markdown>{fixBullets(message.content)}</Markdown>
        )}
      </div>
    </div>
  );
}
