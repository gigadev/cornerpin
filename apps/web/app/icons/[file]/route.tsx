import { ImageResponse } from "next/og";
import { MARK_PARCEL, MARK_PIN } from "@/components/wordmark";
import { ICONS, iconFiles, isIconFile } from "@/lib/icons";

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return iconFiles().map((file) => ({ file }));
}

export async function GET(_request: Request, { params }: { params: Promise<{ file: string }> }) {
  const { file } = await params;
  if (!isIconFile(file)) {
    return new Response("Not found", { status: 404 });
  }
  const { size, maskable } = ICONS[file];
  // Maskable icons fill the square and keep the mark inside the central safe zone.
  const radius = maskable ? 0 : Math.round(size * 0.2);
  const markSize = Math.round(size * (maskable ? 0.5 : 0.68));

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#4f6b4a",
          borderRadius: radius,
        }}
      >
        {/* The wordmark's mark (components/wordmark.tsx), in sand on sage. */}
        <svg width={markSize} height={markSize} viewBox="0 0 24 24">
          <polygon
            points={MARK_PARCEL}
            fill="rgba(247,244,238,0.18)"
            stroke="#f7f4ee"
            strokeWidth={1.75}
            strokeLinejoin="round"
          />
          <circle {...MARK_PIN} fill="#f7f4ee" stroke="#4f6b4a" strokeWidth={1.5} />
        </svg>
      </div>
    ),
    { width: size, height: size },
  );
}
