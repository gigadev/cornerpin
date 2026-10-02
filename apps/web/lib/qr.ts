import QRCode from "qrcode";
import { siteUrl } from "@/lib/site";

// Lot signs (P1-11, ADR-031). The QR code holds /q/{code}, never a lot's URL, so it survives a
// slug rename. Error correction Q still scans with a quarter of the code scuffed or dirty.

export const QR_CODE_PATTERN = /^[a-z0-9]{6,16}$/;

export function signUrl(code: string): URL {
  return new URL(`/q/${code}`, siteUrl());
}

/** "https://cornerpin.app/q/k7m2p9qa" -> "cornerpin.app/q/k7m2p9qa", printed under the code. */
export function shortSignUrl(url: URL): string {
  return `${url.host}${url.pathname}`;
}

/** The QR code as an SVG document that scales to its container. */
export async function qrSvg(text: string): Promise<string> {
  return QRCode.toString(text, { type: "svg", errorCorrectionLevel: "Q", margin: 2 });
}
