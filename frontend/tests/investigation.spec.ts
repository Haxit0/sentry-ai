import { expect, test } from "@playwright/test";

test("AI failure stays explicit while the real simulator works", async ({ page }) => {
  await page.route("**/api/investigations", route => route.fulfill({
    status: 503, contentType: "application/json",
    body: JSON.stringify({ detail: "Agent runtime not configured: Nightshift needs METERLESS_BASE_URL" }),
  }));
  await page.goto("/legacy");
  await expect(page.getByLabel("Supplier", { exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Run AI investigation" }).click();
  await expect(page.getByRole("alert")).toContainText("AI investigation unavailable");
  await expect(page.getByRole("alert")).toContainText("No AI answer was substituted");
  await page.getByRole("button", { name: "Run simulation", exact: true }).click();
  await expect(page.getByText("Simulation complete", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Baseline vs disrupted" })).toContainText("£500");
});

test("unresolved model output is not shown as a recommendation", async ({ page }) => {
  // A transport fixture exercises failed validation presentation, without claiming real inference.
  await page.route("**/api/investigations", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      investigation_id: "test-unresolved", status: "unresolved",
      recommended_strategy: null, explanation: null, supporting_evidence_ids: [],
      validation: { attempts_used: 3, checks: [{ check: "cost_matches", passed: false, detail: "incorrect cost" }], unresolved: ["cost_matches: incorrect cost"] },
      model: { models_used: ["test-model"], calls: 4, receipt_ids: [], signed_receipts: 0 },
      memory: null, plan: [], tool_calls: [], data_source: "fixture", disclaimer: "Test transport fixture.",
    }),
  }));
  await page.goto("/legacy");
  await page.getByRole("button", { name: "Run AI investigation" }).click();
  const panel = page.getByRole("region", { name: "Ask Sentry to explain why" });
  await expect(panel).toContainText("Investigation unresolved");
  await expect(panel).toContainText("No AI recommendation was accepted");
  await expect(panel.getByText("AI recommendation validated", { exact: true })).toHaveCount(0);
  await page.getByLabel("Supplier", { exact: true }).selectOption("SUP-BETA");
  await expect(panel.getByText("Investigation unresolved", { exact: true })).toHaveCount(0);
});

test("validated report exposes explanation, evidence, receipts and memory", async ({ page }) => {
  // Explicit UI-only transport fixture; actual model behavior is tested separately.
  await page.route("**/api/investigations", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      investigation_id: "test-validated", status: "validated",
      recommended_strategy: "expedite_shipping", explanation: "Test explanation citing order:ORD-1002.",
      supporting_evidence_ids: ["order:ORD-1002"],
      validation: { attempts_used: 1, checks: [{ check: "cost_matches", passed: true, detail: "matches exact costs" }], unresolved: [] },
      model: { models_used: ["test-model"], calls: 2, receipt_ids: ["test-receipt"], signed_receipts: 1 },
      memory: { engine: "H-MEM", recalled: [], stored_memory_id: "test-memory" },
      plan: [{ task_id: "test-task", question: "Check affected orders", tool: "orders" }],
      tool_calls: [{ call_id: "test-call", tool: "orders", status: "ok", summary: "Order evidence", evidence_ids: ["order:ORD-1002"], result: { order_id: "ORD-1002" } }],
      data_source: "fixture", disclaimer: "Test transport fixture.",
    }),
  }));
  await page.goto("/legacy");
  await page.getByRole("button", { name: "Run AI investigation" }).click();
  const panel = page.getByRole("region", { name: "Ask Sentry to explain why" });
  await expect(panel).toContainText("AI recommendation validated");
  await expect(panel).toContainText("Test explanation citing order:ORD-1002.");
  await expect(panel).toContainText("validated finding saved");
  await panel.getByText("Evidence and tool results", { exact: true }).click();
  await expect(panel).toContainText("Supporting evidence: order:ORD-1002");
  await panel.getByText("Model receipts", { exact: true }).click();
  await expect(panel.getByText("test-receipt", { exact: true })).toBeVisible();
});
