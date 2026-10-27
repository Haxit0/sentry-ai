import type { Strategy } from "./types";

export const strategyLabels: Record<Strategy, string> = {
  accept_delay: "Accept the delay",
  expedite_shipping: "Expedite shipping",
  alternative_supplier: "Alternative supplier",
};

export const money = (value: string | number) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: Number(value) % 1 === 0 ? 0 : 2,
  }).format(Number(value));

export const date = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
