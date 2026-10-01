import { describe, expect, it } from "vitest";
import { iconFiles } from "@/lib/icons";
import manifest from "./manifest";

describe("web app manifest", () => {
  const m = manifest();

  it("has the fields browsers require to install the app", () => {
    expect(m.name).toBeTruthy();
    expect(m.short_name).toBeTruthy();
    expect(m.start_url).toBe("/");
    expect(m.display).toBe("standalone");
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
