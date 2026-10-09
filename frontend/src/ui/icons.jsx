const P = {
  shield: "M12 2l8 3v6c0 5-3.4 8.7-8 10-4.6-1.300-8-5-8-10V5l8-3z",
  check: "M5 12.500l4.500 4.500L19 7.500",
  alert: "M12 3l10 18H2L12 3zm0 7v5m0 3v.010",
  clock: "M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z",
  lock: "M7 11V8a5 5 0 0110 0v3M6 11h12v9H6z",
  users: "M16 19v-1.500a3.500 3.500 0 00-3.500-3.500h-5A3.500 3.500 0 004 17.500V19M10 11a3 3 0 100-6 3 3 0 000 6zm6.500 8v-1.500a3.500 3.500 0 00-2-3.100M15 5.200a3 3 0 010 5.600",
  device: "M8 3h8a1 1 0 011 1v16a1 1 0 01-1 1H8a1 1 0 01-1-1V4a1 1 0 011-1zm4 15.500v.010",
  moon: "M20 14.500A8 8 0 019.500 4 8.500 8.500 0 1020 14.500z",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
  flag: "M5 21V4m0 0h11l-2 4 2 4H5",
  repeat: "M17 2l4 4-4 4M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4m14 3v2a3 3 0 01-3 3H3",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zm-8 9a8 8 0 0116 0",
  send: "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z",
  home: "M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1v-9z",
  chart: "M4 20V10m6 10V4m6 16v-7m5 7H3",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10 3a3 3 0 100-6 3 3 0 000 6z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.010M3 12h.010M3 18h.010",
  x: "M6 6l12 12M18 6L6 18",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  network: "M12 5a2 2 0 100-4 2 2 0 000 4zM5 21a2 2 0 100-4 2 2 0 000 4zm14 0a2 2 0 100-4 2 2 0 000 4zM12 5v6m0 0l-7 6m7-6l7 6",
  gavel: "M14 13l-8.500 8.500M16 16l6-6-4-4-6 6 4 4zM8 8l6-6 4 4-6 6-4-4z",
  coin: "M12 3a9 9 0 100 18 9 9 0 000-18zm0 4v10m-3-7.500c0-1 1.300-1.500 3-1.500s3 .800 3 1.800-1.300 1.500-3 1.700-3 .800-3 1.800 1.300 1.700 3 1.700 3-.500 3-1.500",
  globe: "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3.500 3 14.500 0 18M12 3c-3 3.500-3 14.500 0 18",
};
export default function Icon({ name, size = 20, stroke = 2, color = "currentColor", style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" style={style} aria-hidden="true">
      <path d={P[name] || P.shield} />
    </svg>
  );
}
