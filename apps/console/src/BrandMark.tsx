/** One vector identity for the workspace and AURA's central instrument. */
export function BrandGlyph() {
  return (
    <g
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <path d="M48 8 79 26q5 3 5 9v26q0 6-5 9L60 81" />
      <path d="m48 88-31-18q-5-3-5-9V35q0-6 5-9L36 15" />
      <path
        d="m48 24 22 38H56l-8-14-8 14H26Z"
        fill="currentColor"
        fillOpacity=".12"
      />
      <path d="M27 40 48 76l21-36M34 62h28" strokeOpacity=".5" />
      <path
        d="M42 11 48 8l6 3M42 85l6 3 6-3"
        className="brand-accent"
        strokeWidth="3.5"
      />
      <circle cx="48" cy="37" r="2" fill="currentColor" stroke="none" />
    </g>
  );
}

export function BrandMark() {
  return (
    <svg viewBox="0 0 96 96" aria-hidden="true" className="brand-mark">
      <BrandGlyph />
    </svg>
  );
}
