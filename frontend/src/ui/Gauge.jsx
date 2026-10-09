const TIER_COLOR = { low: "#16a34a", medium: "#d99100", high: "#dc2626", extreme: "#475569" };

// Semi-circle risk gauge. score is 0..1.
export default function Gauge({ score = 0, tier = "low", size = 180, label = "Risk score" }) {
  const s = Math.max(0, Math.min(1, Number(score) || 0));
  const R = 70, C = Math.PI * R, color = TIER_COLOR[tier] || "#16a34a";
  return (
    <div className="gauge" style={{ width: size }}>
      <svg viewBox="0 0 180 110" width={size} role="img" aria-label={`${label} ${s.toFixed(2)}`}>
        <path d="M20 90 A70 70 0 0 1 160 90" fill="none" stroke="#e3ebea" strokeWidth="14" strokeLinecap="round" />
        <path d="M20 90 A70 70 0 0 1 160 90" fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${C * s} ${C}`} style={{ transition: "stroke-dasharray .8s ease" }} />
        <text x="90" y="82" textAnchor="middle" fontSize="30" fontWeight="800" fill="#0f2a2b">{s.toFixed(2)}</text>
        <text x="90" y="102" textAnchor="middle" fontSize="11" fill="#6b8281">{label}</text>
      </svg>
    </div>
  );
}
