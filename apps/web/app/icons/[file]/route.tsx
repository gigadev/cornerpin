import { ImageResponse } from "next/og";
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
  // Maskable icons fill the square and keep the glyph inside the central safe zone.
  const radius = maskable ? 0 : Math.round(size * 0.2);
  const fontSize = Math.round(size * (maskable ? 0.45 : 0.6));

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#1c1917",
          color: "#fafaf9",
          borderRadius: radius,
          fontSize,
          fontWeight: 700,
        }}
      >
        C
      </div>
    ),
    { width: size, height: size },
  );
}
