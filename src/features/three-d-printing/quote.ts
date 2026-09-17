import type { ThreeDMaterial, ThreeDSettings } from "@/types/threeDPrinting";

export interface QuoteInput {
  material: string;
  weight: number;
  hours: number;
  quantity: number;
  designFee: number;
}

// Record hours and weight are per piece. Design fee is charged once per record.
export function calculateQuote(
  input: QuoteInput,
  settings: ThreeDSettings | undefined,
  materials: ThreeDMaterial[],
  snapshot?: Record<string, unknown>,
) {
  const frozen = snapshot?.settings as Record<string, unknown> | undefined;
  const original = snapshot?.inputs as Record<string, unknown> | undefined;
  const rates =
    snapshot !== undefined
      ? frozen
      : settings && {
          machines: settings.machine_count,
          elecPerMachine: settings.electricity_per_machine_day,
          laborPerDay: settings.labor_per_day,
          lossRate: settings.material_loss_rate,
          profitRate: settings.profit_rate_percent,
        };
  const price =
    snapshot !== undefined
      ? original?.material === input.material
        ? snapshot.material_price_kg
        : null
      : materials.find((m) => m.name === input.material)?.price_per_kg;
  if (
    !rates ||
    price == null ||
    price === "" ||
    [
      "machines",
      "elecPerMachine",
      "laborPerDay",
      "lossRate",
      "profitRate",
    ].some((k) => rates[k] == null || !Number.isFinite(Number(rates[k]))) ||
    Number(rates.machines) <= 0 ||
    !Number.isFinite(Number(price))
  )
    return null;
  if (
    ![input.weight, input.hours, input.quantity, input.designFee].every(
      (v) => typeof v === "number" && Number.isFinite(v) && v >= 0,
    ) ||
    input.quantity < 1
  )
    return null;
  const material =
    (input.weight * Number(rates.lossRate) * Number(price)) / 1000;
  const electricity = (input.hours / 12) * Number(rates.elecPerMachine);
  const labor =
    ((input.hours / 12) * Number(rates.laborPerDay)) / Number(rates.machines);
  const profitRate = Number(rates.profitRate);
  const unit = (material + electricity + labor) * (1 + profitRate / 100);
  return {
    material,
    electricity,
    labor,
    profitRate,
    unit,
    total: unit * input.quantity + input.designFee,
    basis: snapshot !== undefined ? "记录保存的费率" : "当前材料价格与计费设置",
  };
}
