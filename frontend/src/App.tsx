import { useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { request } from "./api";
import type { Health, Order, Simulation, Strategy, Supplier } from "./types";

const labels: Record<Strategy, string> = {
  accept_delay: "Accept the delay",
  expedite_shipping: "Expedite shipping",
  alternative_supplier: "Alternative supplier",
};
const descriptions: Record<Strategy, string> = {
  accept_delay: "Keep the existing supply plan",
  expedite_shipping: "Bring available supply forward",
  alternative_supplier: "Source from a backup supplier",
};
const money = (value: string | number) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: Number(value) % 1 === 0 ? 0 : 2,
  }).format(Number(value));
const date = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));

function Icon({
  name,
  size = 20,
}: {
  name:
    | "shield"
    | "grid"
    | "arrow"
    | "clock"
    | "check"
    | "box"
    | "chart"
    | "info";
  size?: number;
}) {
  const paths: Record<typeof name, ReactNode> = {
    shield: (
      <>
        <path d="M12 3 4 6v5c0 5 8 10 8 10s8-5 8-10V6l-8-3Z" />
        <path d="m8.5 11.5 2.5 2.5 4.5-5" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    arrow: (
      <>
        <path d="M4 12h16M14 6l6 6-6 6" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    box: (
      <>
        <path d="m12 3 9 5-9 5-9-5 9-5ZM3 8v9l9 5 9-5V8M12 13v9M7 5.8l10 5.4" />
      </>
    ),
    chart: (
      <>
        <path d="M4 4v16h16M8 15v-4M12 15V7M16 15v-6" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7v.1" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [delay, setDelay] = useState(5);
  const [result, setResult] = useState<Simulation | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const activeRun = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setInitializing(true);
    setError("");
    Promise.all([
      request<Health>("/api/health", { signal: controller.signal }),
      request<Supplier[]>("/api/suppliers", { signal: controller.signal }),
      request<Order[]>("/api/orders", { signal: controller.signal }),
    ])
      .then(([status, available, currentOrders]) => {
        if (controller.signal.aborted) return;
        if (available.length === 0)
          throw new Error("No suppliers are available in the data source.");
        setHealth(status);
        setSuppliers(available);
        setOrders(currentOrders);
        setSupplierId(available[0].supplier_id);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load the workspace.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setInitializing(false);
      });
    return () => {
      controller.abort();
      activeRun.current?.abort();
    };
  }, [reload]);

  const selectedSupplier = suppliers.find(
    (supplier) => supplier.supplier_id === supplierId,
  );
  const resultSupplier = suppliers.find(
    (supplier) => supplier.supplier_id === result?.supplier_id,
  );
  const stale =
    !!result &&
    (result.supplier_id !== supplierId || result.delay_days !== delay);
  const best = result?.recovery_options.find(
    (option) => option.strategy === result.recommended_strategy,
  );
  const largestCost = Math.max(
    1,
    ...(result?.recovery_options.map((option) =>
      Number(option.total_estimated_cost_gbp),
    ) ?? []),
  );
  const scopedOrders = orders.filter(
    (order) => order.supplier_id === (result?.supplier_id ?? supplierId),
  );

  async function runSimulation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supplierId || running) return;
    activeRun.current?.abort();
    const controller = new AbortController();
    activeRun.current = controller;
    setRunning(true);
    setError("");
    try {
      const response = await request<Simulation>("/api/simulations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_id: supplierId, delay_days: delay }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setResult(response);
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : "Simulation failed. Please try again.",
        );
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a href="#simulator" className="brand" aria-label="Sentry AI home">
          <span className="brand-mark">
            <Icon name="shield" size={26} />
          </span>
          <span>
            Sentry<span className="brand-ai">AI</span>
            <small>SUPPLY CHAIN INTELLIGENCE</small>
          </span>
        </a>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          <a href="#simulator" className="nav-link active">
            <Icon name="grid" />
            What-If simulator
            <span className="nav-dot" />
          </a>
          <a href="#recovery" className="nav-link">
            <Icon name="chart" />
            Recovery strategies
          </a>
          <a href="#evidence" className="nav-link">
            <Icon name="box" />
            Evidence & assumptions
          </a>
        </nav>
        <div className="sidebar-note">
          <span className="eyebrow">BUILT TO EXPLAIN WHY</span>
          <p>Every recommendation starts with evidence.</p>
          <div className="note-rule" />
          <span className="sidebar-small">
            Open Agent Hackathon 2026
            <br />
            Track 2 · Shared starter
          </span>
        </div>
        <div className="system-status">
          <span className={`status-dot ${health ? "" : "offline"}`} />
          <div>
            <strong>
              {health
                ? "Fixture API connected"
                : initializing
                  ? "Connecting to API"
                  : "API unavailable"}
            </strong>
            <small>Synthetic development environment</small>
          </div>
        </div>
      </aside>

      <main className="main-content" id="simulator">
        <header className="topbar">
          <div>
            <span className="breadcrumb-muted">Workspace</span>
            <span className="breadcrumb-separator">/</span>What-If simulator
          </div>
          <div className="topbar-right">
            <span className="fixture-badge">
              <span />
              SYNTHETIC DATA
            </span>
            {health && (
              <span className="evaluation-date">
                As of {date(health.as_of_date)} {health.as_of_date.slice(0, 4)}
              </span>
            )}
          </div>
        </header>
        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">DISRUPTION → DECISION</div>
              <h1>A clearer path through disruption.</h1>
              <p>
                See the impact of a supplier delay. Compare your options. Know
                why.
              </p>
            </div>
            <span className="workspace-tag">
              <Icon name="shield" size={16} />
              Scenario workspace
            </span>
          </div>

          <section className="scenario-panel" aria-labelledby="scenario-title">
            <div className="section-heading">
              <div className="heading-inline">
                <span className="step">01</span>
                <h2 id="scenario-title">Build your scenario</h2>
              </div>
              <span className="subtle">Deterministic calculations · GBP</span>
            </div>
            <form onSubmit={runSimulation}>
              <div className="scenario-controls">
                <div className="supplier-field">
                  <label htmlFor="supplier">Supplier</label>
                  <select
                    id="supplier"
                    value={supplierId}
                    disabled={initializing || running || !suppliers.length}
                    onChange={(event) => setSupplierId(event.target.value)}
                  >
                    {!suppliers.length && (
                      <option value="">
                        {initializing
                          ? "Loading suppliers…"
                          : "Suppliers unavailable"}
                      </option>
                    )}
                    {suppliers.map((supplier) => (
                      <option
                        key={supplier.supplier_id}
                        value={supplier.supplier_id}
                      >
                        {supplier.name} · {supplier.supplier_id}
                      </option>
                    ))}
                  </select>
                  <span className="field-hint">
                    {selectedSupplier
                      ? `${selectedSupplier.sku} · Planned restock ${date(selectedSupplier.restock_date)}`
                      : "Supplier records are retrieved from the API."}
                  </span>
                </div>
                <div className="delay-field">
                  <div className="range-label">
                    <label htmlFor="delay">Supplier delay</label>
                    <output htmlFor="delay">
                      {delay}
                      <span> days</span>
                    </output>
                  </div>
                  <input
                    id="delay"
                    type="range"
                    min="0"
                    max="30"
                    step="1"
                    value={delay}
                    disabled={initializing || running}
                    onChange={(event) => setDelay(Number(event.target.value))}
                    style={
                      {
                        "--range-fill": `${(delay / 30) * 100}%`,
                      } as CSSProperties
                    }
                  />
                  <div className="range-ticks">
                    <span>0 days</span>
                    <span>15 days</span>
                    <span>30 days</span>
                  </div>
                </div>
                <button
                  className="run-button"
                  type="submit"
                  disabled={initializing || running || !supplierId}
                >
                  {running ? (
                    <>
                      <span className="spinner" />
                      Calculating…
                    </>
                  ) : (
                    <>
                      <span>Run simulation</span>
                      <Icon name="arrow" size={18} />
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>

          {error && (
            <div className="error-banner" role="alert">
              <Icon name="info" />
              <div>
                <strong>We couldn’t complete that request.</strong>
                <p>{error}</p>
                {!suppliers.length && (
                  <button
                    className="text-button"
                    onClick={() => setReload((value) => value + 1)}
                  >
                    Retry connection
                  </button>
                )}
              </div>
            </div>
          )}

          <div aria-live="polite" aria-busy={running}>
            {result && best ? (
              <>
                <div className="results-heading">
                  <div className="heading-inline">
                    <span className="step">02</span>
                    <h2>Scenario impact</h2>
                    <span className="result-label">
                      {resultSupplier?.name ?? result.supplier_id} · +
                      {result.delay_days} days
                    </span>
                  </div>
                  <span
                    className={`run-state ${stale || running ? "pending" : ""}`}
                  >
                    <span />
                    {running
                      ? "Calculating new scenario"
                      : stale
                        ? "Inputs changed · run to update"
                        : "Simulation complete"}
                  </span>
                </div>
                {(stale || running) && (
                  <p className="stale-notice">
                    The results below show the last completed scenario:{" "}
                    {result.supplier_id}, {result.delay_days} days of delay.
                  </p>
                )}
                <section
                  className={`summary-grid ${stale || running ? "previous-results" : ""}`}
                  aria-label="Financial impact summary"
                >
                  <div className="summary-card exposure">
                    <div className="metric-label">
                      Penalty exposure <Icon name="clock" size={17} />
                    </div>
                    <strong>
                      {money(result.estimated_penalty_exposure_gbp)}
                    </strong>
                    <p>Estimated cost if you accept the delay</p>
                  </div>
                  <div className="summary-card">
                    <div className="metric-label">
                      Recommended recovery <Icon name="shield" size={17} />
                    </div>
                    <strong>{money(best.total_estimated_cost_gbp)}</strong>
                    <p>{labels[best.strategy]}</p>
                  </div>
                  <div className="summary-card savings">
                    <div className="metric-label">
                      Potential saving <Icon name="chart" size={17} />
                    </div>
                    <strong>{money(best.saving_vs_no_action_gbp)}</strong>
                    <p>Compared with taking no action</p>
                  </div>
                  <div className="summary-card">
                    <div className="metric-label">
                      Orders arriving late <Icon name="box" size={17} />
                    </div>
                    <strong>
                      {result.affected_orders.length}
                      <span className="metric-denominator">
                        {" "}
                        / {scopedOrders.length}
                      </span>
                    </strong>
                    <p>Selected supplier · before recovery</p>
                  </div>
                </section>

                <section
                  className="recovery-section"
                  id="recovery"
                  aria-labelledby="recovery-title"
                >
                  <div className="section-heading">
                    <div>
                      <h2 id="recovery-title">
                        Three options. One clear comparison.
                      </h2>
                      <p className="section-description">
                        Ranked by total estimated cost, including any remaining
                        late penalties.
                      </p>
                    </div>
                    <span className="subtle">Lowest cost first</span>
                  </div>
                  <div className="strategy-grid">
                    {result.recovery_options.map((option, index) => {
                      const recommended =
                        option.strategy === result.recommended_strategy;
                      return (
                        <article
                          key={option.strategy}
                          className={`strategy-card ${recommended ? "recommended" : ""}`}
                        >
                          <div className="strategy-card-top">
                            <span className="strategy-rank">0{index + 1}</span>
                            {recommended ? (
                              <span className="recommended-label">
                                <Icon name="check" size={13} />
                                RECOMMENDED
                              </span>
                            ) : (
                              <span className="strategy-type">
                                {option.strategy === "accept_delay"
                                  ? "BASELINE"
                                  : "RECOVERY OPTION"}
                              </span>
                            )}
                          </div>
                          <h3>{labels[option.strategy]}</h3>
                          <p className="strategy-description">
                            {descriptions[option.strategy]}
                          </p>
                          <div className="strategy-total">
                            {money(option.total_estimated_cost_gbp)}
                            <span>total estimated cost</span>
                          </div>
                          <div className="cost-track" aria-hidden="true">
                            <span
                              style={{
                                width: `${(Number(option.total_estimated_cost_gbp) / largestCost) * 100}%`,
                              }}
                            />
                          </div>
                          <dl className="cost-breakdown">
                            <div>
                              <dt>Action cost</dt>
                              <dd>{money(option.action_cost_gbp)}</dd>
                            </div>
                            <div>
                              <dt>Remaining penalties</dt>
                              <dd>{money(option.residual_penalty_gbp)}</dd>
                            </div>
                          </dl>
                          <p
                            className={`strategy-saving ${Number(option.saving_vs_no_action_gbp) < 0 ? "negative" : ""}`}
                          >
                            {Number(option.saving_vs_no_action_gbp) >= 0
                              ? `${money(option.saving_vs_no_action_gbp)} saved vs no action`
                              : `${money(-Number(option.saving_vs_no_action_gbp))} more than no action`}
                          </p>
                          <details>
                            <summary>How this is calculated</summary>
                            <p>{option.details}</p>
                          </details>
                        </article>
                      );
                    })}
                  </div>
                </section>

                <section
                  className="orders-panel"
                  aria-labelledby="orders-title"
                >
                  <div className="section-heading">
                    <div>
                      <h2 id="orders-title">
                        Affected customer orders{" "}
                        <span className="count-badge">
                          {result.affected_orders.length}
                        </span>
                      </h2>
                      <p className="section-description">
                        Late orders after available inventory is allocated to
                        the earliest promises.
                      </p>
                    </div>
                    <span className="subtle">
                      Disrupted restock · {date(result.disrupted_restock_date)}
                    </span>
                  </div>
                  {result.affected_orders.length ? (
                    <div className="table-scroll">
                      <table>
                        <caption className="sr-only">
                          Affected orders before recovery, including quantities,
                          delivery dates and estimated penalties
                        </caption>
                        <thead>
                          <tr>
                            <th>Customer / order</th>
                            <th>Quantity / stock</th>
                            <th>Promised</th>
                            <th>Expected</th>
                            <th>Delay</th>
                            <th className="numeric">Penalty</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.affected_orders.map((order) => (
                            <tr key={order.order_id}>
                              <td>
                                <strong>{order.customer_name}</strong>
                                <span>
                                  {order.order_id} · {order.sku}
                                </span>
                              </td>
                              <td>
                                <strong>{order.quantity} units</strong>
                                <span>
                                  {order.inventory_allocated} allocated ·{" "}
                                  {order.shortfall_units} short
                                </span>
                              </td>
                              <td>{date(order.promised_date)}</td>
                              <td>{date(order.expected_delivery_date)}</td>
                              <td>
                                <span className="delay-chip">
                                  +{order.delay_days}{" "}
                                  {order.delay_days === 1 ? "day" : "days"}
                                </span>
                              </td>
                              <td className="numeric penalty-cell">
                                {money(order.estimated_penalty_gbp)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="no-impact">
                      <span className="no-impact-icon">
                        <Icon name="check" size={24} />
                      </span>
                      <div>
                        <h3>All orders remain on time.</h3>
                        <p>
                          There is no estimated late-delivery exposure in this
                          scenario.
                        </p>
                      </div>
                    </div>
                  )}
                </section>

                <section
                  className="evidence-panel"
                  id="evidence"
                  aria-labelledby="evidence-title"
                >
                  <div className="section-heading">
                    <div className="heading-inline">
                      <Icon name="box" />
                      <h2 id="evidence-title">
                        The evidence behind the decision
                      </h2>
                    </div>
                    <span className="subtle">
                      {result.evidence.length} evidence records
                    </span>
                  </div>
                  <div className="evidence-list">
                    {result.evidence.map((item) => (
                      <details key={item.evidence_id}>
                        <summary>
                          <span className="evidence-id">
                            {item.evidence_id}
                          </span>
                          <span>{item.source}</span>
                          <span className="evidence-expand">+</span>
                        </summary>
                        <p>{item.description}</p>
                      </details>
                    ))}
                  </div>
                  <div className="disclosure">
                    <Icon name="info" size={18} />
                    <p>
                      {result.disclaimer} Execution mode:{" "}
                      {result.execution_mode}. Agent status:{" "}
                      {result.agent_status}.
                    </p>
                  </div>
                </section>
              </>
            ) : (
              <section className="empty-state">
                <div className="empty-illustration">
                  <Icon name="shield" size={42} />
                  <span className="orbit-dot" />
                </div>
                <span className="eyebrow">READY WHEN YOU ARE</span>
                <h2>Test a disruption. Find a way forward.</h2>
                <p>
                  Choose a supplier and a delay, then run your first scenario.
                  <br />
                  Sentry will calculate order impact and compare three recovery
                  paths.
                </p>
                <div className="empty-flow">
                  <span>Supplier delay</span>
                  <Icon name="arrow" size={16} />
                  <span>Order impact</span>
                  <Icon name="arrow" size={16} />
                  <span>Recovery decision</span>
                </div>
              </section>
            )}
          </div>

          <footer className="footer">
            <p>
              <span className="footer-dot" />
              Synthetic fixture data only. Zetaris, Meterless Nightshift,
              Meterless Engine and NVIDIA integrations are pending.
            </p>
            <span>Deterministic simulator · v0.1</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
