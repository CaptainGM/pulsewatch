export default function Logo({ size = 36 }) {
  return (
    <span className="brand-logo" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 64 64" width="100%" height="100%">
        <defs>
          <linearGradient id="brand-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#5df3c3" />
            <stop offset="1" stopColor="#19b98d" />
          </linearGradient>
        </defs>
        <path
          d="M10 34h10l5-13 9 25 6-18 4 6h10"
          fill="none"
          stroke="url(#brand-gradient)"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
