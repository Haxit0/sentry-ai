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

test("step navigation reaches each section and history closes with Escape", async ({ page }) => {
  const steps=page.getByRole("navigation",{name:"Investigation steps"});
  await steps.getByRole("link",{name:/03 Decision/}).click();
  await expect(page).toHaveURL(/#results$/);
  await expect(page.getByRole("heading",{name:"Make an informed decision"})).toBeInViewport();
  await steps.getByRole("link",{name:/01 Scenario/}).click();
  await expect(page).toHaveURL(/#scenario$/);
  await page.getByRole("button",{name:"Open run history",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"Investigation history"})).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog",{name:"Investigation history"})).not.toBeVisible();
});

test("exploring the calculated delay chart does not alter scenario inputs", async ({ page }) => {
  await page.getByRole("button",{name:"Compare calculated options"}).click();
  const chartSlider=page.getByRole("slider",{name:"Explore calculated delay"});
  await chartSlider.focus();
  await chartSlider.press("End");
  await expect(chartSlider).toHaveValue("30");
  await expect(page.getByRole("slider",{name:"Supplier delay: 5 days"})).toHaveValue("5");
  await expect(page.getByRole("region",{name:"Changing decisions"})).toContainText("Exploring this chart does not change your scenario");
});

test("edited inputs leave a clear warning on the previous calculation", async ({ page }) => {
  await page.getByRole("button",{name:"Compare calculated options"}).click();
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("£160.00");
  await page.getByRole("slider",{name:"Supplier delay: 5 days"}).press("ArrowRight");
  await expect(page.getByText("Your controls have changed.")).toBeVisible();
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("£160.00");
});

test("history can be searched on a narrow screen with no page overflow", async ({ page }) => {
  await page.setViewportSize({width:375,height:812});
  await page.route("**/api/v2/investigation-runs",route=>route.fulfill({contentType:"application/json",body:JSON.stringify([{id:"run-verified-example",status:"validated",created_at:"2026-10-27T20:00:00Z"},{id:"run-cancelled-example",status:"cancelled",created_at:"2026-10-27T19:00:00Z"}])}));
  await page.getByRole("button",{name:"Refresh connections and history"}).click();
  await page.getByRole("button",{name:"Open run history",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Investigation history"});
  await dialog.getByRole("textbox",{name:"Search investigation history"}).fill("validated");
  await expect(dialog.getByRole("button",{name:"run-verified-example"})).toBeVisible();
  await expect(dialog.getByRole("button",{name:"run-cancelled-example"})).toHaveCount(0);
  await page.getByRole("button",{name:"Close history",exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

test("a source failure is explicit and keeps investigation actions unavailable", async ({ page }) => {
  await page.route("**/api/v2/workspace",route=>route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"Zetaris source unavailable for this test"})}));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Zetaris source unavailable");
  await expect(page.getByRole("button",{name:"Run AI investigation"})).toBeDisabled();
  await expect(page.getByRole("button",{name:"Compare calculated options"})).toBeDisabled();
});

for (const width of [1440,768,375,320]) {
  test(`redesigned workspace remains usable at ${width}px`, async ({page}) => {
    await page.emulateMedia({reducedMotion:"reduce"});
    await page.setViewportSize({width,height:1000});
    await page.getByRole("button",{name:"Compare calculated options"}).click();
    await expect(page.getByRole("region",{name:"Decision comparison"})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.getByRole("navigation",{name:"Investigation steps"}).getByRole("link",{name:/01 Scenario/}).click();
    await page.keyboard.press("Control+Home");
    await page.screenshot({path:`../local_data/ui-review/workspace-${width}.png`,fullPage:false});
    await page.getByRole("navigation",{name:"Investigation steps"}).getByRole("link",{name:/03 Decision/}).click();
    await page.screenshot({path:`../local_data/ui-review/decision-${width}.png`,fullPage:false});
  });
}
