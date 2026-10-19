import { describe, expect, it } from "vitest";
import { detectPlatform } from "../src/lib/useOs";

const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15";
describe("detectPlatform", () => {
  it("Mac desktop -> mac", () => expect(detectPlatform(MAC, "MacIntel", 0)).toBe("mac"));
  it("Windows, Linux, ChromeOS, Android -> pc", () => {
    expect(detectPlatform("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130", "Win32")).toBe("pc");
    expect(detectPlatform("Mozilla/5.0 (X11; Linux x86_64) Firefox/130", "Linux x86_64")).toBe("pc");
    expect(detectPlatform("Mozilla/5.0 (X11; CrOS x86_64) Chrome/130", "")).toBe("pc");
    expect(detectPlatform("Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile", "Linux armv8l")).toBe("pc");
  });
  it("iPhone and iPad (including iPadOS posing as a Mac) -> pc", () => {
    expect(detectPlatform("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari", "iPhone")).toBe("pc");
    expect(detectPlatform(MAC, "MacIntel", 5)).toBe("pc");
  });
});
