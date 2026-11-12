interface Props {
  progress: number;
  stage: string;
}

export default function ProgressBar({ progress, stage }: Props) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 16, boxShadow: "var(--shadow-soft)" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 8,
          fontSize: 14,
        }}
      >
        <span style={{ color: "var(--text-soft)" }}>{stage}</span>
        <span style={{ color: "var(--brand)", fontWeight: 800 }}>{progress}%</span>
      </div>
      <div
        style={{
          height: 8,
          background: "var(--input-bg)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progress}%`,
            background: "var(--brand)",
            borderRadius: 4,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}
