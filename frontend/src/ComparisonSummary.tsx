import { deliveryChange, exposureChange } from "./comparison";
import type { SimulationComparison } from "./comparison";
import { date, money, strategyLabels } from "./format";

export default function ComparisonSummary({
  baseline,
  disrupted,
}: SimulationComparison) {
  const penaltyChange = exposureChange(
    baseline.estimated_penalty_exposure_gbp,
    disrupted.estimated_penalty_exposure_gbp,
  );
  const orderChange =
    disrupted.affected_orders.length - baseline.affected_orders.length;
  // Explain the backend's selected option; do not rank or select strategies here.
  const recommended = disrupted.recovery_options.find(
    (option) => option.strategy === disrupted.recommended_strategy,
  );
  const otherOptions = disrupted.recovery_options.filter(
    (option) => option.strategy !== disrupted.recommended_strategy,
  );
  const tied = otherOptions.some(
    (option) =>
      option.total_estimated_cost_gbp === recommended?.total_estimated_cost_gbp,
  );

  return (
    <section className="comparison-panel" aria-labelledby="comparison-title">
      <div className="section-heading">
        <div>
          <h2 id="comparison-title">Baseline vs disrupted</h2>
          <p className="section-description">
            Same supplier, before recovery. Both scenarios are calculated by the
            simulation API.
          </p>
        </div>
      </div>
      <div className="table-scroll" tabIndex={0}>
        <table>
          <caption className="sr-only">
            Baseline and disrupted scenario comparison for{" "}
            {disrupted.supplier_id}
          </caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Baseline · 0 days</th>
              <th scope="col">Disrupted · +{disrupted.delay_days} days</th>
              <th scope="col">Change vs baseline</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Estimated penalty exposure</th>
              <td>{money(baseline.estimated_penalty_exposure_gbp)}</td>
              <td>{money(disrupted.estimated_penalty_exposure_gbp)}</td>
              <td className="comparison-change">
                {Number(penaltyChange) > 0 ? "+" : ""}
                {money(penaltyChange)}
              </td>
            </tr>
            <tr>
              <th scope="row">Affected orders</th>
              <td>{baseline.affected_orders.length}</td>
              <td>{disrupted.affected_orders.length}</td>
              <td className="comparison-change">
                {orderChange > 0 ? "+" : ""}
                {orderChange} {Math.abs(orderChange) === 1 ? "order" : "orders"}
              </td>
            </tr>
            <tr>
              <th scope="row">Supplier restock date</th>
              <td>{date(baseline.disrupted_restock_date)}</td>
              <td>{date(disrupted.disrupted_restock_date)}</td>
              <td className="comparison-change">
                {deliveryChange(
                  baseline.disrupted_restock_date,
                  disrupted.disrupted_restock_date,
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        className="comparison-explanation"
        role="note"
        aria-label="Scenario explanation"
      >
        <p>
          With a {disrupted.delay_days}-day supplier delay for{" "}
          {disrupted.supplier_id}, estimated penalty exposure{" "}
          {penaltyChange === "0.00"
            ? `stays at ${money(disrupted.estimated_penalty_exposure_gbp)}`
            : `${penaltyChange.startsWith("-") ? "falls" : "rises"} from ${money(baseline.estimated_penalty_exposure_gbp)} to ${money(disrupted.estimated_penalty_exposure_gbp)}`}
          , while affected orders{" "}
          {orderChange === 0
            ? `stay at ${disrupted.affected_orders.length}`
            : `${orderChange < 0 ? "decrease" : "increase"} from ${baseline.affected_orders.length} to ${disrupted.affected_orders.length}`}
          .
        </p>
        {recommended && (
          <p>
            The backend recommends {strategyLabels[recommended.strategy]} at{" "}
            {money(recommended.total_estimated_cost_gbp)} (
            {money(recommended.action_cost_gbp)} action costs and{" "}
            {money(recommended.residual_penalty_gbp)} remaining penalties),{" "}
            {tied ? "tied for the lowest" : "the lowest"} returned total. Other
            totals:{" "}
            {otherOptions
              .map(
                (option) =>
                  `${strategyLabels[option.strategy]} ${money(option.total_estimated_cost_gbp)}`,
              )
              .join("; ")}
            .
          </p>
        )}
      </div>
    </section>
  );
}
