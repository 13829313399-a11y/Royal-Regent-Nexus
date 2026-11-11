import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import DailyAmountChart from "../components/DailyAmountChart.vue";
import { costComposition, currency } from "../dashboardPresentation";

const base = { materialCost: 12, electricityCost: 3, laborCost: 15, maintenanceCost: 7, totalCost: 37 };
describe("3D dashboard presentation", () => {
  it("keeps legacy daily labor and maintenance separate and reads incompleteness from the outer summary", () => {
    const legacyDisplay = { ...base, totalCost: 30, incompleteCostRecordCount: 99 };
    const view = costComposition({ ...base, legacyDisplay, incompleteCostRecordCount: 2 });
    expect(view.mode).toBe("ready");
    expect(view.total).toBe(30);
    expect(view.items.map(i => i.percent)).toEqual([40, 10, 50]);
    expect(view.maintenance).toBe(7);
    expect(view.incomplete).toBe(2);
    expect(costComposition({ ...base, legacyDisplay: false }).legacy).toBe(false);
    expect(costComposition(base).items.map(i => i.value)).toEqual([12, 3, 15, 7]);
  });
  it("accepts three cents of rounding and rejects larger differences", () => {
    expect(costComposition({ ...base, totalCost: 37.03 }).mode).toBe("ready");
    expect(costComposition({ ...base, materialCost: 1e12, totalCost: 1e12 + 25.03 }).mode).toBe("ready");
    expect(costComposition({ ...base, totalCost: 37.031 }).mode).toBe("invalid");
    expect(costComposition({ ...base, totalCost: 36.96 }).items.every(i => i.arc === 0)).toBe(true);
  });
  it("distinguishes zero spending from missing or invalid amounts", () => {
    const zero = { materialCost: 0, electricityCost: 0, laborCost: 0, maintenanceCost: 0, totalCost: 0 };
    expect(costComposition(zero).mode).toBe("empty");
    for (const value of [NaN, Infinity, -1, undefined, null]) {
      const s = { ...zero, materialCost: value as number };
      const view = costComposition(s);
      expect(view.mode).toBe("invalid");
      expect(view.items[0]?.value).toBe(value);
      expect(view.items.every(i => i.percent === undefined)).toBe(true);
    }
    expect(currency(0)).toBe("¥0.00");
    expect(currency(null)).toBe("—");
    expect(currency(-2)).toBe("¥-2.00");
  });
  it("places gains above the zero line and losses below it, and exposes each signed amount to the keyboard", async () => {
    const days = [80, -25, 0].map((balance, i) => ({ date: "2026-11-0" + (i + 1), revenue: 80, totalCost: 20, balance }));
    const chart = mount(DailyAmountChart, { props: { days, balance: true }, attachTo: document.body });
    try {
      const zero = parseFloat((chart.get(".grid-line.zero").element as HTMLElement).style.top);
      const bars = chart.findAll<HTMLElement>(".bar");
      expect(parseFloat(bars[0]!.element.style.top)).toBeLessThan(zero);
      expect(parseFloat(bars[1]!.element.style.top)).toBe(zero);
      expect(bars[2]!.classes()).toContain("mark");
      const buttons = chart.findAll("button");
      expect(buttons.filter(button => button.attributes("tabindex") === "0")).toHaveLength(1);
      await buttons[0]!.trigger("mouseenter");
      await buttons[1]!.trigger("focus");
      expect(chart.get(".chart-value").text()).toContain("¥-25.00");
      await buttons[1]!.trigger("keydown", { key: "End" });
      expect(document.activeElement).toBe(buttons[2]!.element);
    } finally { chart.unmount(); }
  });
});
