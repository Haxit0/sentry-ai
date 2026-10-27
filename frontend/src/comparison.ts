import { request } from "./api";
import type { Simulation } from "./types";

export interface SimulationComparison {
  baseline: Simulation;
  disrupted: Simulation;
}

export async function runComparison(
  supplierId: string,
  delayDays: number,
  signal: AbortSignal,
): Promise<SimulationComparison> {
  const simulate = (delay: number) =>
    request<Simulation>("/api/simulations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ supplier_id: supplierId, delay_days: delay }),
      signal,
    });

  const baselineRequest = simulate(0);
  const [baseline, disrupted] = await Promise.all([
    baselineRequest,
    delayDays === 0 ? baselineRequest : simulate(delayDays),
  ]);
  return { baseline, disrupted };
}

/**
 * Display-only subtraction of two backend-computed, two-decimal GBP values.
 * Integer pence keep the displayed delta exact; Number is for formatting only.
 * The backend owns penalty models, recovery costs and strategy selection.
 * Never recalculate those models or choose a strategy in the frontend.
 */
export function exposureChange(baseline: string, disrupted: string): string {
  const pence = (value: string) => BigInt(value.replace(".", ""));
  const difference = pence(disrupted) - pence(baseline);
  const absolute = difference < 0n ? -difference : difference;
  return `${difference < 0n ? "-" : ""}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}

export function deliveryChange(baseline: string, disrupted: string): string {
  const days = Math.round(
    (Date.parse(`${disrupted}T00:00:00Z`) -
      Date.parse(`${baseline}T00:00:00Z`)) /
      86_400_000,
  );
  if (days === 0) return "No change";
  return `${Math.abs(days)} ${Math.abs(days) === 1 ? "day" : "days"} ${days > 0 ? "later" : "earlier"}`;
}
