// Countdown ring. value = seconds left, total = full duration.
export default function Ring({ value, total = 30, size = 52, color = "#dc2626" }) {
  const r = (size - 8) / 2, c = 2 * Math.PI * r, p = total ? Math.max(0, Math.min(1, value / total)) : 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${c * p} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: "stroke-dasharray 1s linear" }} />
      <text x="50%" y="55%" textAnchor="middle" dominantBaseline="middle" fontSize="15" fontWeight="700" fill="#fff">{value}</text>
    </svg>
  );
}
