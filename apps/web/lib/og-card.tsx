import { ImageResponse } from "next/og";
import { MARK_PARCEL, MARK_PIN } from "@/components/wordmark";

// Link-preview cards (P1-07) in the site's colours (ADR-033). Shared by the subdivision and lot
// opengraph-image routes. Satori draws them with its default font, not the site's.

export const OG_SIZE = { width: 1200, height: 630 };

export function ogCard({ eyebrow, title, lines }: { eyebrow: string; title: string; lines: string[] }) {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "#f7f4ee",
          color: "#1f2a33",
          borderTop: "16px solid #4f6b4a",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 36, color: "#4f6b4a" }}>{eyebrow}</div>
          <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.1 }}>{title}</div>
          {lines.map((line) => (
            <div key={line} style={{ fontSize: 44 }}>
              {line}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 32, fontWeight: 700 }}>
          <svg width={44} height={44} viewBox="0 0 24 24">
            <polygon
              points={MARK_PARCEL}
              fill="rgba(79,107,74,0.15)"
              stroke="#4f6b4a"
              strokeWidth={1.75}
              strokeLinejoin="round"
            />
            <circle {...MARK_PIN} fill="#4f6b4a" stroke="#f7f4ee" strokeWidth={1.5} />
          </svg>
          Cornerpin
        </div>
      </div>
    ),
    OG_SIZE,
  );
}
