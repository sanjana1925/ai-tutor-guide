// Purely decorative geometric accents. Always aria-hidden and pointer-events-none
// so they never interfere with usability or screen readers.

export function DecoStar({ className = "", color = "#8B5CF6", size = 36, ...rest }) {
  return (
    <svg
      aria-hidden="true"
      className={`pointer-events-none absolute ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      {...rest}
    >
      <path
        d="M12 2l2.4 6.9L22 9.3l-5.6 4.9 1.8 7-6.2-3.9-6.2 3.9 1.8-7L2 9.3l7.6-.4z"
        fill={color}
        stroke="#1E293B"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function DecoDots({ className = "", color = "#1E293B", ...rest }) {
  const pts = [
    [4, 4],
    [16, 4],
    [28, 4],
    [4, 16],
    [16, 16],
    [28, 16],
    [4, 28],
    [16, 28],
    [28, 28],
  ];
  return (
    <svg
      aria-hidden="true"
      className={`pointer-events-none absolute ${className}`}
      width="36"
      height="36"
      viewBox="0 0 32 32"
      {...rest}
    >
      {pts.map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="2" fill={color} opacity="0.35" />
      ))}
    </svg>
  );
}

export function DecoSquiggle({ className = "", color = "#1E293B", width = 90, ...rest }) {
  return (
    <svg
      aria-hidden="true"
      className={`pointer-events-none absolute ${className}`}
      width={width}
      height={22}
      viewBox="0 0 90 22"
      fill="none"
      {...rest}
    >
      <path d="M3 14 Q13 2 23 14 T43 14 T63 14 T83 14" stroke={color} strokeWidth="3.5" strokeLinecap="round" />
    </svg>
  );
}
