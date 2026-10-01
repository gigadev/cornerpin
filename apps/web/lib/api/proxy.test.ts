import { describe, expect, it } from "vitest";
import { forwardRequestHeaders, forwardResponseHeaders } from "./proxy";

describe("forwardRequestHeaders", () => {
  it("passes the session cookie, origin and body type, and nothing else", () => {
    const incoming = new Headers({
      cookie: "cp_session=abc",
      origin: "http://localhost:3300",
      "content-type": "application/json",
      host: "localhost:3300",
      authorization: "Bearer should-not-pass",
    });
    const forwarded = forwardRequestHeaders(incoming, null);
    expect(forwarded.get("cookie")).toBe("cp_session=abc");
    expect(forwarded.get("origin")).toBe("http://localhost:3300");
    expect(forwarded.get("content-type")).toBe("application/json");
    expect(forwarded.has("host")).toBe(false);
    expect(forwarded.has("authorization")).toBe(false);
  });

  it("keeps an existing x-forwarded-for, else uses the client address", () => {
    expect(
      forwardRequestHeaders(new Headers({ "x-forwarded-for": "1.2.3.4" }), "5.6.7.8").get(
        "x-forwarded-for",
      ),
    ).toBe("1.2.3.4");
    expect(forwardRequestHeaders(new Headers(), "5.6.7.8").get("x-forwarded-for")).toBe("5.6.7.8");
  });
});

describe("forwardResponseHeaders", () => {
  it("keeps every set-cookie and marks the response uncacheable", () => {
    const upstream = new Headers();
    upstream.append("set-cookie", "cp_session=abc; HttpOnly; Path=/");
    upstream.append("set-cookie", "cp_oauth=; Max-Age=0; Path=/v1/auth/google");
    upstream.set("content-type", "application/json");
    upstream.set("server", "uvicorn");

    upstream.set("content-disposition", 'attachment; filename="Recorded plat.pdf"');

    const headers = forwardResponseHeaders(upstream);
    expect(headers.getSetCookie()).toHaveLength(2);
    expect(headers.get("content-disposition")).toContain("Recorded plat.pdf");
    expect(headers.get("cache-control")).toBe("no-store");
    expect(headers.has("server")).toBe(false);
  });
});
