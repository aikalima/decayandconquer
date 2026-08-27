import { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";
import { sendChatMessage } from "../api/client";
import type { ChatMessage, ToolResult } from "../api/client";
import ChartCanvas from "../components/ChartCanvas";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  toolResults?: ToolResult[];
  loading?: boolean;
}

const markdownStyles = `
.chat-markdown p { margin: 4px 0; }
.chat-markdown ul, .chat-markdown ol { margin: 4px 0; padding-left: 20px; }
.chat-markdown li { margin: 2px 0; }
.chat-markdown strong { color: var(--text); }
.chat-markdown code { background: var(--input-bg); padding: 1px 5px; border-radius: 3px; font-size: 11px; color: var(--brand-hover); }
.chat-markdown pre { background: var(--input-bg); padding: 8px 10px; border-radius: 6px; overflow-x: auto; margin: 6px 0; }
.chat-markdown pre code { padding: 0; background: none; }
.chat-markdown h1, .chat-markdown h2, .chat-markdown h3 { margin: 8px 0 4px; font-size: 13px; color: var(--text); }
.chat-markdown table { border-collapse: collapse; margin: 6px 0; width: 100%; }
.chat-markdown th, .chat-markdown td { border: 1px solid var(--border); padding: 3px 8px; text-align: left; font-size: 11px; }
.chat-markdown th { background: var(--surface-subtle); color: var(--text-muted); }
.chat-markdown blockquote { border-left: 3px solid var(--brand); margin: 6px 0; padding-left: 10px; color: var(--text-muted); }
.chat-markdown a { color: var(--brand); }
`;

export default function ChatPage() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [allToolResults, setAllToolResults] = useState<ToolResult[]>([]);
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

      // Accumulate tool results for chart canvas
      if (result.tool_results.length > 0) {
        setAllToolResults((prev) => [...prev, ...result.tool_results]);
      }
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
    <div style={{ display: "flex", height: "100%", gap: 0 }}>
      <style>{markdownStyles}</style>
      {/* Left: Chat */}
      <div
        style={{
          width: 420,
          minWidth: 350,
          display: "flex",
          flexDirection: "column",
              borderRight: "1px solid var(--border)",
        }}
      >
        {/* Messages */}
        <div
          style={{
            flex: 1,
            overflow: "auto",
            padding: "12px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {messages.length === 0 && (
            <div style={{ color: "var(--text-muted)", fontSize: 12, padding: "20px 0" }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>💬</div>
              <p style={{ margin: "0 0 10px", color: "var(--text-muted)" }}>
                Ask about stocks, options, predictions. Try:
              </p>
              {[
                "What are the top theta plays right now?",
                "Predict where NVDA will be in 60 days",
                "Which tickers have the highest options volume?",
                "Compare AAPL, MSFT and TSLA for next month",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  style={{
                    display: "block",
                    width: "100%",
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "7px 12px",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    fontSize: 11,
                    textAlign: "left",
                    marginBottom: 6,
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
            padding: "6px 16px 10px",
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="Ask about stocks..."
            disabled={loading}
            style={{
              flex: 1,
              padding: "9px 12px",
              borderRadius: 8,
              border: "1px solid var(--border-strong)",
              background: "var(--input-bg)",
              color: "var(--text)",
              fontSize: 13,
              outline: "none",
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              padding: "9px 16px",
              borderRadius: 8,
              border: "none",
              background: loading ? "var(--surface-hover)" : "var(--brand)",
              color: "var(--text-on-accent)",
              cursor: loading ? "wait" : "pointer",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {loading ? "..." : "Send"}
          </button>
        </div>
      </div>

      {/* Right: Chart Canvas */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: 16,
          background: "var(--page-bg)",
        }}
      >
        <ChartCanvas toolResults={allToolResults} />
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  const isUser = message.role === "user";

  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start" }}>
      <div
        className={isUser ? undefined : "chat-markdown"}
        style={{
          maxWidth: "90%",
          padding: "8px 12px",
          borderRadius: 10,
          background: isUser ? "var(--brand)" : "var(--card-bg)",
          color: isUser ? "var(--text-on-accent)" : "var(--text)",
          fontSize: 12,
          lineHeight: 1.6,
        }}
      >
        {message.loading ? (
          <span style={{ color: "var(--text-muted)" }}>Thinking...</span>
        ) : isUser ? (
          message.content
        ) : (
          <Markdown>{message.content}</Markdown>
        )}
      </div>
    </div>
  );
}
