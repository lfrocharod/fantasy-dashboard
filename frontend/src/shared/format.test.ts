import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dateTime, fmt, lastName, money, pct, relTime, signed, timeUntil } from "./format";

describe("number formatting", () => {
  it("renders missing or non-finite numbers as a dash", () => {
    expect(fmt(null)).toBe("–");
    expect(fmt(Number.NaN)).toBe("–");
    expect(signed(undefined)).toBe("–");
    expect(money(null)).toBe("–");
  });
  it("signs, rounds and scales", () => {
    expect(fmt(3.14159, 2)).toBe("3.14");
    expect(signed(2)).toBe("+2.0");
    expect(signed(-0.25, 2)).toBe("-0.25");
    expect(signed(0, 0)).toBe("+0");
    expect(money(7.5)).toBe("€7.5m");
    expect(pct(0.423)).toBe("42%");
  });
  it("keeps the surname", () => {
    expect(lastName("Kylian Mbappé")).toBe("Mbappé");
    expect(lastName(null)).toBe("–");
  });
});

describe("times", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-21T12:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("counts down to a deadline", () => {
    expect(timeUntil("2026-10-22T15:30:00Z")).toBe("1d 3h");
    expect(timeUntil("2026-10-21T14:45:00Z")).toBe("2h 45m");
    expect(timeUntil("2026-10-21T11:00:00Z")).toBe("deadline passed");
    expect(timeUntil(null)).toBe("–");
  });
  it("describes how long ago", () => {
    expect(relTime("2026-10-21T11:59:45Z")).toBe("just now");
    expect(relTime("2026-10-21T11:15:00Z")).toBe("45m ago");
    expect(relTime("2026-10-21T07:00:00Z")).toBe("5h ago");
    expect(relTime("2026-10-18T12:00:00Z")).toBe("3d ago");
    expect(relTime(null)).toBe("never");
  });
  it("shows wall-clock times in Mexico City", () => {
    // 19:00 UTC is 13:00 in Mexico City (UTC-6, no DST since 2022)
    expect(dateTime("2026-10-21T19:00:00Z")).toBe("21 Oct, 13:00");
  });
});
