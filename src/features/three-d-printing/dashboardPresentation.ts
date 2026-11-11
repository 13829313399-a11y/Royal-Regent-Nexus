import type { ThreeDDashboard } from "@/types/threeDPrinting";

export type Summary = ThreeDDashboard["summary"];
export type ChartDay = { date: string; revenue: number; totalCost: number; balance: number };

export const isAmount = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

export function currency(value: unknown) {
  return isAmount(value) ? "¥" + value.toFixed(2) : "—";
}

export function displayStats(summary: Summary): Summary {
  const legacy = summary.legacyDisplay;
  return legacy && typeof legacy === "object" && !Array.isArray(legacy) ? legacy as Summary : summary;
}

const parts = [
  { key: "materialCost", label: "材料", color: "var(--tdp-material)" },
  { key: "electricityCost", label: "电费", color: "var(--tdp-electricity)" },
  { key: "laborCost", label: "人工", color: "var(--tdp-labor)" },
  { key: "maintenanceCost", label: "维修", color: "var(--tdp-maintenance)" },
] as const;

export function costComposition(summary: Summary) {
  const stats = displayStats(summary);
  const legacy = stats !== summary;
  const total = stats.totalCost;
  const rows = (legacy ? parts.slice(0, 3) : parts).map(part => ({ ...part, value: stats[part.key] }));
  const amounts = rows.map(row => row.value);
  const sum = amounts.reduce<number>((n, value) => n + (isAmount(value) ? value : 0), 0);
  // API currency is rounded to cents. Compare those integers so that exactly
  // three cents remains valid at large magnitudes. Retain any finer precision.
  const exactCents = (n: unknown) => isAmount(n) && Number.isSafeInteger(Math.round(n * 100)) && Math.round(n * 100) / 100 === n;
  const difference = isAmount(total) && exactCents(total) && amounts.every(exactCents)
    ? Math.abs(amounts.reduce<number>((n, value) => n + Math.round(value! * 100), 0) - Math.round(total * 100)) / 100
    : Math.abs(sum - (total ?? NaN));
  const valid = isAmount(total) && total >= 0 && amounts.every(value => isAmount(value) && value >= 0)
    && difference <= 0.03 && (total === 0) === (sum === 0);
  const mode = !valid ? "invalid" : total === 0 ? "empty" : "ready";
  let offset = 0;
  const items = rows.map(row => {
    const start = offset;
    // The API total is the denominator. A rounding remainder stays on the track.
    const percent = mode === "ready" ? row.value! / total! * 100 : undefined;
    const arc = Math.min(100 - offset, percent ?? 0);
    offset += arc;
    return { ...row, percent, start, arc };
  });
  return { legacy, mode, total, items, maintenance: stats.maintenanceCost, incomplete: summary.incompleteCostRecordCount };
}
