import QRCode from "qrcode";
import { describe, expect, it } from "vitest";
import { QR_CODE_PATTERN, qrSvg, shortSignUrl, signUrl } from "./qr";

describe("sign URLs", () => {
  it("point at /q/{code} on the site", () => {
    const url = signUrl("k7m2p9qa");
    expect(url.pathname).toBe("/q/k7m2p9qa");
    expect(shortSignUrl(new URL("https://cornerpin.app/q/k7m2p9qa"))).toBe(
      "cornerpin.app/q/k7m2p9qa",
    );
  });

  it("accept only well-formed codes", () => {
    expect(QR_CODE_PATTERN.test("k7m2p9qa")).toBe(true);
    expect(QR_CODE_PATTERN.test("K7M2")).toBe(false);
    expect(QR_CODE_PATTERN.test("../app")).toBe(false);
  });
});

describe("qrSvg", () => {
  it("draws a scalable SVG of the code at error correction Q", async () => {
    const text = "https://cornerpin.app/q/k7m2p9qa";
    const svg = await qrSvg(text);
    expect(svg).toMatch(/^<svg[^>]*viewBox="0 0 \d+ \d+"/);
    // Same symbol the library builds for this text at level Q, plus the 2-module margin.
    const size = QRCode.create(text, { errorCorrectionLevel: "Q" }).modules.size + 4;
    expect(svg).toContain(`viewBox="0 0 ${size} ${size}"`);
  });
});
