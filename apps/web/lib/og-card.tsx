import { ImageResponse } from "next/og";

// Link-preview cards (P1-07): plain neutral text until there is a brand. Shared by the
// subdivision and lot opengraph-image routes.

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
          background: "#fafaf9",
          color: "#1c1917",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ fontSize: 36, color: "#57534e" }}>{eyebrow}</div>
          <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.1 }}>{title}</div>
          {lines.map((line) => (
            <div key={line} style={{ fontSize: 44 }}>
              {line}
            </div>
          ))}
        </div>
        <div style={{ fontSize: 32, fontWeight: 700 }}>Cornerpin</div>
      </div>
    ),
    OG_SIZE,
  );
}
