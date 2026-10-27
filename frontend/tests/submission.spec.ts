import { expect, test } from "@playwright/test";

test.setTimeout(120_000);

test.beforeEach(async ({ page }) => {
  await page.route("https://fonts.googleapis.com/**", route => route.abort());
  await page.goto("/");
  await expect(page.getByLabel("Supplier", { exact: true })).toBeEnabled({timeout:90_000});
  await expect(page.getByLabel("Supplier", { exact: true }).locator("option")).toHaveCount(3);
});

test("real v2 comparison explains cost, alternatives and source provenance", async ({ page }) => {
  await page.getByRole("button", { name: "Compare calculated options" }).click();
  const comparison=page.getByRole("region",{name:"Decision comparison"});
  await expect(comparison).toContainText("£500.00");
  await expect(comparison).toContainText("£160.00");
  await expect(page.getByRole("region",{name:"Changing decisions"})).toContainText("At 7 days");
  await page.getByRole("region",{name:"Source uncertainty"}).locator("summary").filter({hasText:"Data provenance"}).click();
  await expect(page.getByRole("region",{name:"Source uncertainty"})).toContainText("Snapshot");
});

test("budget and deadline can leave no feasible recovery", async ({ page }) => {
  await page.getByLabel("Demonstration case").selectOption("budget-blocked");
  await page.getByRole("button", { name: "Compare calculated options" }).click();
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("No feasible recovery under these constraints");
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("exceeds the budget");
});

test("source disagreement is explicit and firm recommendation is withheld", async ({ page }) => {
  await page.getByLabel("Demonstration case").selectOption("conflicting-eta");
  await page.getByRole("button", { name: "Compare calculated options" }).click();
  await expect(page.getByRole("region",{name:"Source uncertainty"})).toContainText("Confirm the current expected arrival");
  await expect(page.getByRole("region",{name:"Source uncertainty"})).toContainText("3–5-day delay range");
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("withheld");
});

test("a queued AI run can be cancelled without presenting a recommendation", async ({ page }) => {
  const run={id:"run-ui-test",status:"running",request:{supplier_id:"SUP-ALPHA",delay_days:5,case_id:"alpha-delay",max_action_cost_gbp:null,max_late_days:null,compare_strategy:"alternative_supplier"},events:[{at:"test",agent:"planner",message:"Testing queued run display"}],report:null,error:null,cancelled:0,review:null};
  await page.route("**/api/v2/investigation-runs",route=>route.request().method()==="POST"?route.fulfill({status:202,contentType:"application/json",body:JSON.stringify(run)}):route.continue());
  await page.route("**/api/v2/investigation-runs/run-ui-test",route=>route.fulfill({contentType:"application/json",body:JSON.stringify(run)}));
  await page.route("**/api/v2/investigation-runs/run-ui-test/cancel",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({...run,status:"cancelled",cancelled:1})}));
  await page.getByRole("button",{name:"Run AI investigation"}).click();
  await expect(page.getByRole("region",{name:"AI investigation"})).toContainText("Run status: running");
  await page.getByRole("button",{name:"Cancel investigation"}).click();
  await expect(page.getByRole("region",{name:"AI investigation"})).toContainText("Run status: cancelled");
  await expect(page.getByRole("button",{name:"Approve recommendation"})).toBeDisabled();
});

test("narrow-screen workbench does not overflow", async ({ page }) => {
  await page.setViewportSize({width:375,height:812});
  await page.getByRole("button", { name: "Compare calculated options" }).click();
  await expect(page.getByRole("region",{name:"Decision comparison"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
