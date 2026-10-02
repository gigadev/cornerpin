import { describe, expect, it } from "vitest";
import { iconFiles } from "@/lib/icons";
import { portalManifest, siteManifest, subdivisionManifest } from "./manifests";

const manifests = {
  site: siteManifest(),
  subdivision: subdivisionManifest({ slug: "juniper-bench", name: "Juniper Bench" }),
  portal: portalManifest(),
};

describe.each(Object.entries(manifests))("the %s manifest", (_name, m) => {
  it("has the fields browsers require to install the app", () => {
    expect(m.name).toBeTruthy();
    expect(m.short_name).toBeTruthy();
    expect(m.id).toBeTruthy();
    expect(m.display).toBe("standalone");
  });

  it("starts inside its own scope", () => {
    expect(m.start_url?.startsWith(m.scope ?? "")).toBe(true);
  });

  it("offers 192 and 512 pixel PNG icons and a maskable icon", () => {
    const icons = m.icons ?? [];
    const sizes = icons.map((icon) => icon.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
    expect(icons.some((icon) => icon.purpose === "maskable")).toBe(true);
    expect(icons.every((icon) => icon.type === "image/png")).toBe(true);
  });

  it("points only at icons the icon route generates", () => {
    const served = iconFiles().map((file) => `/icons/${file}`);
    for (const icon of m.icons ?? []) {
      expect(served).toContain(icon.src);
    }
  });
});

describe("scopes", () => {
  it("give each subdivision and the portal their own app", () => {
    expect(manifests.subdivision).toMatchObject({
      id: "/juniper-bench/",
      start_url: "/juniper-bench",
      scope: "/juniper-bench",
      short_name: "Juniper Bench",
    });
    expect(manifests.portal).toMatchObject({ id: "/app/", start_url: "/app", scope: "/app" });
    expect(manifests.site).toMatchObject({ id: "/", start_url: "/", scope: "/" });
  });
});
