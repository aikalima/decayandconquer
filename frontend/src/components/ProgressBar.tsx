interface Props {
  progress: number;
  stage: string;
}

export default function ProgressBar({ progress, stage }: Props) {
  return (
    <div style={{ background: "#1a1a2e", borderRadius: 8, padding: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 8,
          fontSize: 13,
        }}
      >
        <span style={{ color: "#aaa" }}>{stage}</span>
        <span style={{ color: "#6c63ff", fontWeight: 600 }}>{progress}%</span>
      </div>
      <div
        style={{
          height: 8,
          background: "#0f0f1a",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progress}%`,
            background: "linear-gradient(90deg, #6c63ff, #4a90d9)",
            borderRadius: 4,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}
