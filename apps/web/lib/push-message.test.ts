import { describe, expect, it } from "vitest";
import { applicationServerKey, parsePushMessage, sameOriginUrl } from "./push-message";

describe("parsePushMessage", () => {
  it("accepts a title, body and url", () => {
    const message = { title: "Lot 7 · Juniper Bench", body: "Is now sold", url: "/x" };
    expect(parsePushMessage(message)).toEqual(message);
  });

  it("refuses anything else", () => {
    expect(parsePushMessage(null)).toBeNull();
    expect(parsePushMessage({ title: "Lot 7", body: 3, url: "/x" })).toBeNull();
  });
});

describe("sameOriginUrl", () => {
  const origin = "https://cornerpin.app";

  it("keeps pages on this site", () => {
    expect(sameOriginUrl("https://cornerpin.app/juniper-bench/lots/7", origin)).toBe(
      "https://cornerpin.app/juniper-bench/lots/7",
    );
    expect(sameOriginUrl("/account", origin)).toBe("https://cornerpin.app/account");
  });

  it("sends anything else to the home page", () => {
    expect(sameOriginUrl("https://evil.example/phish", origin)).toBe(origin);
    expect(sameOriginUrl(42, origin)).toBe(origin);
  });
});

describe("applicationServerKey", () => {
  it("decodes unpadded base64url", () => {
    expect([...applicationServerKey("-_8")]).toEqual([0xfb, 0xff]);
    const vapidPublicKey =
      "BJBOCM5AxWJYTIrNwT96CXm1Xr227x0zlifXp3Jaf-hXEbIebHUcwLq9M9I9EgDCAB8y1E4h_Stz9uwJF_BqtJk";
    expect(applicationServerKey(vapidPublicKey)).toHaveLength(65);
  });
});
