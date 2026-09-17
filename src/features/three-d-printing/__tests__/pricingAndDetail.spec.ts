import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { calculateQuote } from "../quote";
import {
  chinaTime,
  freshestPrinter,
  groupPrinterEvents,
} from "../printerPresentation";
import QuoteEditor from "../components/QuoteEditor.vue";
import type {
  ThreeDMaterial,
  ThreeDPrinter,
  ThreeDSettings,
} from "@/types/threeDPrinting";
const settings = {
  machine_count: 11,
  electricity_per_machine_day: 1.5,
  labor_per_day: 220,
  material_loss_rate: 1.2,
  profit_rate_percent: 40,
} as ThreeDSettings;
const materials = [{ name: "PETG 灰色", price_per_kg: 21 }] as ThreeDMaterial[];
const input = {
  material: "PETG 灰色",
  weight: 55,
  hours: 1.37,
  quantity: 1,
  designFee: 0,
};
const snapshot = {
  settings: {
    machines: 11,
    elecPerMachine: 1.5,
    laborPerDay: 220,
    lossRate: 1.2,
    profitRate: 40,
  },
  material_price_kg: "21",
  inputs: { material: "PETG 灰色" },
};

describe("Legacy quote contract", () => {
  it("reproduces the supplied 55g / 1.37h legacy record price of 5.38", () => {
    expect(calculateQuote(input, settings, materials)?.unit.toFixed(2)).toBe(
      "5.38",
    );
  });
  it("multiplies per-piece costs once and adds design fee once", () => {
    const one = calculateQuote(input, settings, materials)!;
    const batch = calculateQuote(
      { ...input, quantity: 3, designFee: 10 },
      settings,
      materials,
    )!;
    expect(batch.unit).toBe(one.unit);
    expect(batch.total).toBeCloseTo(one.unit * 3 + 10, 8);
  });
  it("uses stored record rates and never current rates for historical corrections", () => {
    expect(
      calculateQuote(
        input,
        { ...settings, profit_rate_percent: 100 },
        [],
        snapshot,
      )?.unit.toFixed(2),
    ).toBe("5.38");
    expect(calculateQuote(input, settings, materials, {})).toBeNull();
    expect(
      calculateQuote(
        { ...input, material: "PLA" },
        settings,
        materials,
        snapshot,
      ),
    ).toBeNull();
  });
  it("does not invent a zero material price, but accepts explicitly free material", () => {
    expect(calculateQuote(input, settings, [])).toBeNull();
    expect(
      calculateQuote(input, settings, [{ ...materials[0]!, price_per_kg: 0 }])
        ?.material,
    ).toBe(0);
    expect(
      calculateQuote({ ...input, quantity: 0 }, settings, materials),
    ).toBeNull();
    expect(
      calculateQuote({ ...input, weight: NaN }, settings, materials),
    ).toBeNull();
  });
  it("keeps saved quotes on opening, recalculates after input, and respects manual entry", async () => {
    const w = mount(QuoteEditor, {
      props: {
        modelValue: 20,
        input,
        settings,
        materials,
        existing: true,
        snapshot,
      },
    });
    expect(w.emitted("update:modelValue")).toBeUndefined();
    await w.setProps({ input: { ...input } });
    expect(w.emitted("update:modelValue")).toBeUndefined();
    await w.setProps({ input: { ...input, weight: 110 } });
    expect(w.emitted("update:modelValue")?.at(-1)).toEqual([7.32]);
    await w.get("input").setValue("30");
    const count = w.emitted("update:modelValue")!.length;
    await w.setProps({ input: { ...input, weight: 165 } });
    expect(w.emitted("update:modelValue")).toHaveLength(count);
    await w.get("button").trigger("click");
    expect(w.emitted("update:modelValue")?.at(-1)).toEqual([9.26]);
    w.unmount();
  });
});

describe("Readable printer observations", () => {
  it("honors stale evidence from either source at equal device time and accepts later recovery", () => {
    const online = {
      last_seen_at: "2026-09-17T06:17:56Z",
      connected: true,
      status_stale: false,
    } as ThreeDPrinter;
    const stale = { ...online, connected: false, status_stale: true };
    expect(freshestPrinter(online, stale)).toBe(stale);
    expect(freshestPrinter(stale, online)).toBe(stale);
    const newer = { ...online, last_seen_at: "2026-09-17T06:18:00Z" };
    expect(freshestPrinter(newer, stale)).toBe(newer);
  });
  const event = (
    id: string,
    state: string,
    second: number,
    file = "a.3mf",
    session = "a",
  ) => ({
    id,
    state,
    observed_at: `2026-09-17T06:17:${String(second).padStart(2, "0")}+00:00`,
    current_file: file,
    connection_session_id: session,
  });
  it("merges adjacent duplicates but retains state changes, tasks and sessions", () => {
    const groups = groupPrinterEvents([
      event("1", "FINISH", 56),
      event("2", "FINISH", 50),
      event("3", "RUNNING", 40),
      event("4", "FINISH", 30),
      event("5", "FINISH", 20, "b.3mf"),
      event("6", "FINISH", 10, "b.3mf", "b"),
    ]);
    expect(groups.map((g) => g.count)).toEqual([2, 1, 1, 1, 1]);
  });
  it("never bridges a long missing-data interval", () => {
    const a = event("1", "FINISH", 56),
      b = { ...event("2", "FINISH", 20), observed_at: "2026-09-17T06:10:20Z" };
    expect(groupPrinterEvents([b, a])).toHaveLength(2);
  });
  it("shows China time instead of raw UTC or browser timezone", () => {
    expect(chinaTime("2026-09-17T06:17:56.512+00:00")).toContain("14:17:56");
    expect(chinaTime("")).toBe("暂无上报");
  });
});
