import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

test.setTimeout(120_000);
async function openStepTwo(page:import("@playwright/test").Page) {
  await page.goto("/");
  await expect(page.getByRole("button",{name:"A delivery is late"})).toBeEnabled({timeout:90_000});
  await page.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(page.getByLabel("Supplier",{exact:true})).toBeEnabled({timeout:90_000});
}
async function preview(page:import("@playwright/test").Page) {
  await page.getByRole("button",{name:"Just compare costs, without AI"}).click();
  await expect(page.getByRole("heading",{name:"Here's your next move."})).toBeVisible();
}
test.beforeEach(async({page})=>{await page.route("https://fonts.googleapis.com/**",r=>r.abort());});

test("first visit shows one clear starting point and no wall of results",async({page})=>{
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"What do you need help with?"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Continue",exact:true})).toBeVisible();
  await expect(page.getByRole("slider")).toHaveCount(0);
  await expect(page.getByRole("region",{name:"Decision comparison"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Find my best option"})).toHaveCount(0);
});

test("a cost preview has one plain answer and hides the details until requested",async({page})=>{
  await openStepTwo(page);await preview(page);
  const answer=page.getByRole("article",{name:"Your answer"});
  await expect(answer).toContainText("Speed up the shipment");
  await expect(answer).toContainText("£160.00");
  await expect(answer).toContainText("£500.00");
  await expect(answer).toContainText("AI was not used");
  await expect(page.getByRole("region",{name:"Decision comparison"})).not.toBeVisible();
  await page.getByText("Compare the three options",{exact:true}).click();
  await expect(page.getByRole("region",{name:"Decision comparison"})).toContainText("£260.00");
  await page.getByText("What if the delay changes?",{exact:true}).click();
  await expect(page.getByRole("region",{name:"Changing decisions"})).toContainText("At 7 days");
  await page.getByText("See how we reached this",{exact:true}).click();
  const evidence=page.getByRole("region",{name:"Source uncertainty"});
  await evidence.locator("summary").filter({hasText:"Data provenance"}).click();
  await expect(evidence).toContainText("Snapshot");
});

test("budget case never presents an unsuitable plan as acceptable",async({page})=>{
  await page.goto("/");await page.getByRole("button",{name:"Recovery costs too much"}).click();
  await page.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(page.getByRole("heading",{name:"What are your recovery limits?"})).toBeVisible();
  await expect(page.getByLabel("Maximum spending")).toBeVisible();
  await expect(page.getByRole("slider",{name:"Delivery delay"})).toHaveCount(0);
  await page.getByRole("button",{name:"Just compare costs, without AI"}).click();
  await expect(page.getByRole("article",{name:"Your answer"})).toContainText("No option fits your budget and deadline");
  await expect(page.getByRole("button",{name:"Approve this plan"})).toHaveCount(0);
});

test("conflicting sources lead with the question a human must answer",async({page})=>{
  await page.goto("/");await page.getByRole("button",{name:"Arrival reports disagree"}).click();
  await page.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Let's check the arrival reports."})).toBeVisible();
  await expect(page.getByText("Supplier's update",{exact:true})).toBeVisible({timeout:90_000});
  await expect(page.getByText("Carrier's update",{exact:true})).toBeVisible();
  await expect(page.getByRole("slider",{name:"Delivery delay"})).toHaveCount(0);
  await page.getByRole("button",{name:"Preview reports, without AI"}).click();
  await expect(page.getByRole("heading",{name:"One detail needs checking."})).toBeVisible();
  await expect(page.getByRole("article",{name:"Your answer"})).toContainText("Confirm the current expected arrival");
  await expect(page.getByRole("button",{name:"Approve this plan"})).toHaveCount(0);
});

test("delay buttons change the value and exploring a chart doesn't change inputs",async({page})=>{
  await openStepTwo(page);
  await page.getByRole("button",{name:"Increase delay by one day"}).click();
  await expect(page.getByRole("slider",{name:"Delivery delay"})).toHaveValue("6");
  await page.getByRole("button",{name:"Reduce delay by one day"}).click();await preview(page);
  await page.getByText("What if the delay changes?",{exact:true}).click();
  const slider=page.getByRole("slider",{name:"Explore calculated delay"});await slider.press("End");await expect(slider).toHaveValue("30");
  await page.getByRole("button",{name:"Change the details"}).click();
  await expect(page.getByRole("slider",{name:"Delivery delay"})).toHaveValue("5");
});

test("a running check is visible, cancellable, and never offers approval",async({page})=>{
  await openStepTwo(page);
  const run={id:"run-guided-test",status:"running",request:{supplier_id:"SUP-ALPHA",delay_days:5,case_id:"alpha-delay",max_action_cost_gbp:null,max_late_days:null,compare_strategy:"alternative_supplier"},events:[{at:"test",agent:"planner",message:"Choosing evidence questions"}],report:null,error:null,cancelled:0,review:null};
  await page.route("**/api/v2/investigation-runs",r=>r.request().method()==="POST"?r.fulfill({status:202,contentType:"application/json",body:JSON.stringify(run)}):r.continue());
  await page.route("**/api/v2/investigation-runs/run-guided-test",r=>r.fulfill({contentType:"application/json",body:JSON.stringify(run)}));
  await page.route("**/api/v2/investigation-runs/run-guided-test/cancel",r=>r.fulfill({contentType:"application/json",body:JSON.stringify({...run,status:"cancelled",cancelled:1})}));
  await page.getByRole("button",{name:"Find my best option"}).click();
  await expect(page.getByRole("heading",{name:"We're checking your options."})).toBeVisible();
  await expect(page.getByRole("slider")).toHaveCount(0);
  await page.getByRole("button",{name:"Cancel check"}).click();
  await expect(page.getByText("Check cancelled. You can change the details and try again.")).toBeVisible();
  await expect(page.getByRole("button",{name:"Approve this plan"})).toHaveCount(0);
});

test("past checks support search and Escape without leaving the guided task",async({page})=>{
  await page.route("**/api/v2/investigation-runs",r=>r.fulfill({contentType:"application/json",body:JSON.stringify([{id:"run-example-a",status:"validated",created_at:"2026-10-27T20:00:00Z"},{id:"run-example-b",status:"cancelled",created_at:"2026-10-27T19:00:00Z"}])}));
  await page.goto("/");await page.getByRole("button",{name:"Past checks",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Past checks"});await dialog.getByRole("textbox",{name:"Search past checks"}).fill("validated");
  await expect(dialog).toContainText("run-example-a");await expect(dialog).not.toContainText("run-example-b");
  await page.keyboard.press("Escape");await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("heading",{name:"What do you need help with?"})).toBeVisible();
});

test("unavailable data keeps the main check disabled with an explicit error",async({page})=>{
  await page.route("**/api/v2/workspace",r=>r.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"Data source unavailable for this test"})}));
  await page.goto("/");await page.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Data source unavailable");
  await expect(page.getByRole("button",{name:"Find my best option"})).toBeDisabled();
});

for(const width of [1440,768,375,320]) {
  test(`guided task fits ${width}px with one screen visible at a time`,async({page})=>{
    await page.emulateMedia({reducedMotion:"reduce"});await page.setViewportSize({width,height:1000});
    await page.goto("/");await expect(page.getByRole("button",{name:"Continue",exact:true})).toBeEnabled();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:fileURLToPath(new URL(`../../local_data/guide-review/start-${width}.png`,import.meta.url))});
    await page.getByRole("button",{name:"Continue",exact:true}).click();
    await expect(page.getByRole("button",{name:"Find my best option"})).toBeEnabled({timeout:90000});
    await page.screenshot({path:fileURLToPath(new URL(`../../local_data/guide-review/setup-${width}.png`,import.meta.url))});
    await preview(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:fileURLToPath(new URL(`../../local_data/guide-review/answer-${width}.png`,import.meta.url))});
    await expect(page.getByRole("slider",{name:"Delivery delay"})).toHaveCount(0);
  });
}
