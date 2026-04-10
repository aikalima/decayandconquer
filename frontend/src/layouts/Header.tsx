export default function Header() {
  return (
    <header
      style={{
        height: 56,
        background: "#1a1a2e",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        borderBottom: "1px solid #2a2a4a",
      }}
    >
      <div style={{ display: "flex", alignItems: "center" }}>
        <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.5 }}>
          Decay <span style={{ color: "#6c63ff" }}>And Conquer</span>
        </span>
      </div>

      <div style={{ display: "flex", gap: 12 }} />
    </header>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "6px 16px",
  borderRadius: 6,
  border: "1px solid #444",
  background: "transparent",
  color: "#ccc",
  cursor: "pointer",
  fontSize: 13,
};
