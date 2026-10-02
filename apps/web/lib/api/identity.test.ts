import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const fetchMock = vi.fn();

beforeEach(() => {
  vi.resetModules();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("apiAuthHeaders", () => {
  it("adds nothing locally", async () => {
    vi.stubEnv("API_AUDIENCE", "");
    const { apiAuthHeaders } = await import("./identity");
    expect(await apiAuthHeaders()).toEqual({});
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks the metadata server for an ID token once, then reuses it", async () => {
    vi.stubEnv("API_AUDIENCE", "https://api-123.us-west1.run.app");
    fetchMock.mockResolvedValue(new Response("token-abc"));
    const { apiAuthHeaders } = await import("./identity");

    expect(await apiAuthHeaders()).toEqual({ authorization: "Bearer token-abc" });
    expect(await apiAuthHeaders()).toEqual({ authorization: "Bearer token-abc" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("audience=https%3A%2F%2Fapi-123.us-west1.run.app");
    expect(init.headers).toEqual({ "Metadata-Flavor": "Google" });
  });

  it("fails loudly when there is no token", async () => {
    vi.stubEnv("API_AUDIENCE", "https://api-123.us-west1.run.app");
    fetchMock.mockResolvedValue(new Response("nope", { status: 404 }));
    const { apiAuthHeaders } = await import("./identity");
    await expect(apiAuthHeaders()).rejects.toThrow("Could not get an ID token: 404");
  });
});
