// Shared v1 wire types. Coordinate changes with backend/app/schemas.py and docs/CONTRACT.md.
export type Money = string;
export type Strategy =
  | "accept_delay"
  | "expedite_shipping"
  | "alternative_supplier";

export interface Supplier {
  supplier_id: string;
  name: string;
  sku: string;
  restock_date: string;
  replenishment_quantity: number;
  expedite: {
    days_saved: number;
    capacity_units: number;
    fixed_fee_gbp: Money;
    per_unit_fee_gbp: Money;
  };
  alternative: {
    supplier_name: string;
    lead_time_days: number;
    capacity_units: number;
    fixed_fee_gbp: Money;
    unit_premium_gbp: Money;
  };
}

export interface Order {
  order_id: string;
  customer_name: string;
  supplier_id: string;
  sku: string;
  quantity: number;
  promised_date: string;
  penalty_per_day_gbp: Money;
}

export interface AffectedOrder extends Order {
  inventory_allocated: number;
  shortfall_units: number;
  expected_delivery_date: string;
  delay_days: number;
  estimated_penalty_gbp: Money;
}

export interface RecoveryOption {
  strategy: Strategy;
  residual_penalty_gbp: Money;
  action_cost_gbp: Money;
  total_estimated_cost_gbp: Money;
  saving_vs_no_action_gbp: Money;
  details: string;
}

export interface Simulation {
  supplier_id: string;
  delay_days: number;
  as_of_date: string;
  disrupted_restock_date: string;
  affected_orders: AffectedOrder[];
  estimated_penalty_exposure_gbp: Money;
  recovery_options: RecoveryOption[];
  recommended_strategy: Strategy;
  evidence: { evidence_id: string; source: string; description: string }[];
  execution_mode: "fixture";
  agent_status: "not_configured";
  disclaimer: string;
}

export interface Health {
  status: "ok";
  execution_mode: "fixture";
  as_of_date: string;
  agent_status: "not_configured";
  integrations: { zetaris: "not_configured"; meterless: "not_configured" };
}
