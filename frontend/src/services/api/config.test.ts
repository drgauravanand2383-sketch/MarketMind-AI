import { describe, expect, it } from "vitest";
import { API_BASE_URL, validateRequiredUrl, WS_BASE_URL } from "@/services/api/config";

describe("validateRequiredUrl", () => {
  it("falls back to the dev default when unset in dev mode", () => {
    expect(validateRequiredUrl("VITE_API_BASE_URL", undefined, true, "http://localhost:8000/api/v1", ["http:", "https:"])).toBe(
      "http://localhost:8000/api/v1",
    );
  });

  it("throws a clear error when unset outside dev mode", () => {
    expect(() => validateRequiredUrl("VITE_API_BASE_URL", undefined, false, "http://localhost:8000/api/v1", ["http:", "https:"])).toThrow(
      /Missing required environment variable "VITE_API_BASE_URL"/,
    );
  });

  it("throws the same missing-var error for VITE_WS_BASE_URL, naming that key specifically", () => {
    expect(() => validateRequiredUrl("VITE_WS_BASE_URL", undefined, false, "ws://localhost:8000/ws", ["ws:", "wss:"])).toThrow(
      /Missing required environment variable "VITE_WS_BASE_URL"/,
    );
  });

  it("throws when the configured value is not a valid URL", () => {
    expect(() => validateRequiredUrl("VITE_API_BASE_URL", "not a url", false, "http://localhost:8000/api/v1", ["http:", "https:"])).toThrow(
      /not a valid URL/,
    );
  });

  it("throws when the URL's protocol isn't one of the expected schemes", () => {
    expect(() => validateRequiredUrl("VITE_WS_BASE_URL", "https://api.example.com/ws", false, "ws://localhost:8000/ws", ["ws:", "wss:"])).toThrow(
      /protocol/,
    );
  });

  it("accepts and returns a well-formed value unchanged", () => {
    expect(
      validateRequiredUrl("VITE_API_BASE_URL", "https://api.example.com/api/v1", false, "http://localhost:8000/api/v1", ["http:", "https:"]),
    ).toBe("https://api.example.com/api/v1");
  });

  it("accepts either http: or https: for the API URL, and either ws: or wss: for the WS URL", () => {
    expect(validateRequiredUrl("VITE_API_BASE_URL", "http://api.example.com/api/v1", false, "", ["http:", "https:"])).toBe(
      "http://api.example.com/api/v1",
    );
    expect(validateRequiredUrl("VITE_WS_BASE_URL", "ws://api.example.com/ws", false, "", ["ws:", "wss:"])).toBe("ws://api.example.com/ws");
  });
});

describe("API_BASE_URL / WS_BASE_URL", () => {
  it("resolve to valid URLs in this (dev/test-mode) environment", () => {
    expect(() => new URL(API_BASE_URL)).not.toThrow();
    expect(() => new URL(WS_BASE_URL)).not.toThrow();
  });
});
