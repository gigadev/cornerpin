// The Cornerpin mark: a lot's boundary with a survey pin at one corner (ADR-033). The icon
// route (app/icons) draws the same shape.

export const MARK_PARCEL = "5,7.5 19.5,4.5 20,19.5 4,18";
export const MARK_PIN = { cx: 5, cy: 7.5, r: 3 };

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <polygon
        points={MARK_PARCEL}
        fill="currentColor"
        fillOpacity={0.12}
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      <circle {...MARK_PIN} fill="currentColor" stroke="var(--background)" strokeWidth={1.5} />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2">
      <Mark className="size-6 text-primary" />
      <span className="font-heading text-xl font-semibold tracking-tight">Cornerpin</span>
    </span>
  );
}
