import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page, Route } from "@playwright/test";
import type { Simulation } from "../src/types";
import { strategyLabels } from "../src/format";

const comparison = (page: Page) =>
  page.getByRole("region", { name: "Baseline vs disrupted" });
const explanation = (page: Page) =>
  comparison(page).getByRole("note", { name: "Scenario explanation" });

async function openWorkspace(page: Page) {
  // External typography is optional; keep tests independent of Google Fonts.
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByLabel("Supplier", { exact: true })).toBeEnabled();
}

async function setDelay(page: Page, value: number) {
  const slider = page.getByRole("slider", { name: "Supplier delay" });
  await slider.focus();
  await slider.press("Home");
  for (let day = 0; day < value; day += 1) await slider.press("ArrowRight");
  await expect(slider).toHaveValue(String(value));
}

async function run(page: Page) {
  await page.getByRole("button", { name: "Run simulation" }).click();
  await expect(
    page.getByText("Simulation complete", { exact: true }),
  ).toBeVisible();
}

async function simulate(
  request: APIRequestContext,
  supplierId: string,
  delayDays: number,
): Promise<Simulation> {
  const response = await request.post("/api/simulations", {
    data: { supplier_id: supplierId, delay_days: delayDays },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

const money = (value: string) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: Number(value) % 1 === 0 ? 0 : 2,
  }).format(Number(value));

async function expectExposure(
  page: Page,
  baseline: Simulation,
  disrupted: Simulation,
) {
  await expect(
    comparison(page)
      .getByRole("row", { name: /Estimated penalty exposure/ })
      .getByRole("cell"),
  ).toHaveText([
    money(baseline.estimated_penalty_exposure_gbp),
    money(disrupted.estimated_penalty_exposure_gbp),
    `${Number(disrupted.estimated_penalty_exposure_gbp) > Number(baseline.estimated_penalty_exposure_gbp) ? "+" : ""}${money(
      String(
        Number(disrupted.estimated_penalty_exposure_gbp) -
          Number(baseline.estimated_penalty_exposure_gbp),
      ),
    )}`,
  ]);
}

async function expectExplanation(
  page: Page,
  baseline: Simulation,
  disrupted: Simulation,
) {
  const note = explanation(page);
  await expect(note).toContainText(
    `With a ${disrupted.delay_days}-day supplier delay for ${disrupted.supplier_id}`,
  );
  await expect(note).toContainText(
    money(baseline.estimated_penalty_exposure_gbp),
  );
  await expect(note).toContainText(
    money(disrupted.estimated_penalty_exposure_gbp),
  );
  const selected = disrupted.recovery_options.find(
    (option) => option.strategy === disrupted.recommended_strategy,
  )!;
  await expect(note).toContainText(
    `The backend recommends ${strategyLabels[selected.strategy]} at ${money(selected.total_estimated_cost_gbp)}`,
  );
  await expect(note).toContainText(
    `${money(selected.action_cost_gbp)} action costs and ${money(selected.residual_penalty_gbp)} remaining penalties`,
  );
  for (const option of disrupted.recovery_options) {
    if (option.strategy !== selected.strategy) {
      await expect(note).toContainText(
        `${strategyLabels[option.strategy]} ${money(option.total_estimated_cost_gbp)}`,
      );
    }
  }
}

function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

test("compares real baseline and disrupted results and preserves recovery and disclosures", async ({
  page,
  request,
}) => {
  const baseline = await simulate(request, "SUP-ALPHA", 0);
  const disrupted = await simulate(request, "SUP-ALPHA", 5);
  const payloads: unknown[] = [];
  page.on("request", (sent) => {
    if (sent.url().endsWith("/api/simulations"))
      payloads.push(sent.postDataJSON());
  });
  await openWorkspace(page);
  await expect(comparison(page)).toHaveCount(0);
  await run(page);

  expect(payloads).toHaveLength(2);
  expect(payloads).toEqual(
    expect.arrayContaining([
      { supplier_id: "SUP-ALPHA", delay_days: 0 },
      { supplier_id: "SUP-ALPHA", delay_days: 5 },
    ]),
  );
  await expectExposure(page, baseline, disrupted);
  await expectExplanation(page, baseline, disrupted);
  await expect(explanation(page)).toContainText(
    "estimated penalty exposure rises from £0 to £500, while affected orders increase from 0 to 1",
  );
  await expect(explanation(page)).toContainText("the lowest returned total");
  await expect(
    comparison(page)
      .getByRole("row", { name: /Affected orders/ })
      .getByRole("cell"),
  ).toHaveText(["0", "1", "+1 order"]);
  await expect(
    comparison(page)
      .getByRole("row", { name: /Supplier restock date/ })
      .getByRole("cell"),
  ).toHaveText(["27 Oct", "1 Nov", "5 days later"]);
  const order = page.getByRole("row", { name: /ORD-1002/ });
  await expect(order).toContainText("On time by 27 Oct");
  await expect(order).toContainText("1 Nov");
  await expect(order).toContainText("Newly late");
  await expect(order).toContainText("5 days past promise");
  await expect(
    page.getByRole("region", { name: "Financial impact summary" }),
  ).toContainText("£160");
  await expect(
    page.getByText("Synthetic fixture data only.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText(/Agent status: not_configured/)).toBeVisible();
});

test("retains the last complete pair until both updated requests succeed", async ({
  page,
  request,
}) => {
  await openWorkspace(page);
  await run(page);
  const previousExplanation = await explanation(page).textContent();
  await page.getByLabel("Supplier", { exact: true }).selectOption("SUP-BETA");
  await setDelay(page, 7);
  await expect(page.getByText("Inputs changed · run to update")).toBeVisible();
  await expect(
    comparison(page).getByRole("columnheader", { name: "Disrupted · +5 days" }),
  ).toBeVisible();

  const baselineGate = gate();
  const baselineStarted = gate();
  const disruptionReturned = gate();
  const payloads: unknown[] = [];
  await page.route("**/api/simulations", async (route) => {
    const payload = route.request().postDataJSON();
    payloads.push(payload);
    if (payload.delay_days === 0) {
      baselineStarted.release();
      await baselineGate.promise;
    }
    await route.fulfill({ response: await route.fetch() });
    if (payload.delay_days === 7) disruptionReturned.release();
  });
  try {
    await page.getByRole("button", { name: "Run simulation" }).click();
    await Promise.all([baselineStarted.promise, disruptionReturned.promise]);
    await expect(
      page.getByRole("button", { name: "Calculating…" }),
    ).toBeDisabled();
    await expect(page.getByLabel("Supplier", { exact: true })).toBeDisabled();
    await expect(page.getByRole("slider")).toBeDisabled();
    await expect(
      page.getByText("Comparing scenarios", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(/last completed comparison: SUP-ALPHA, 5 days/),
    ).toBeVisible();
    // The disrupted half has returned, but neither half of the old pair changes.
    await expect(
      comparison(page).getByRole("row", { name: /Estimated penalty exposure/ }),
    ).toContainText("£500");
    await expect(
      comparison(page).getByRole("columnheader", {
        name: "Disrupted · +7 days",
      }),
    ).toHaveCount(0);
    await expect(explanation(page)).toHaveText(previousExplanation!);
  } finally {
    baselineGate.release();
  }
  await expect(
    page.getByText("Simulation complete", { exact: true }),
  ).toBeVisible();
  expect(payloads).toEqual(
    expect.arrayContaining([
      { supplier_id: "SUP-BETA", delay_days: 0 },
      { supplier_id: "SUP-BETA", delay_days: 7 },
    ]),
  );
  const baseline = await simulate(request, "SUP-BETA", 0);
  const disrupted = await simulate(request, "SUP-BETA", 7);
  await expectExposure(page, baseline, disrupted);
  await expectExplanation(page, baseline, disrupted);
  await expect(explanation(page)).toContainText(
    `affected orders increase from ${baseline.affected_orders.length} to ${disrupted.affected_orders.length}`,
  );
  await expect(
    page
      .getByRole("table")
      .filter({ has: page.getByText("ORD-1002", { exact: false }) }),
  ).toHaveCount(0);
  await expect(page.getByRole("row", { name: /ORD-1004/ })).toBeVisible();
  await expect(page.locator(".stale-notice")).toHaveCount(0);
});

test("a delay-only update refreshes the comparison; zero delay reuses one real result", async ({
  page,
  request,
}) => {
  await openWorkspace(page);
  await run(page);
  await setDelay(page, 30);
  await expect(page.getByText("Inputs changed · run to update")).toBeVisible();
  await run(page);
  await expectExposure(
    page,
    await simulate(request, "SUP-ALPHA", 0),
    await simulate(request, "SUP-ALPHA", 30),
  );
  await expectExplanation(
    page,
    await simulate(request, "SUP-ALPHA", 0),
    await simulate(request, "SUP-ALPHA", 30),
  );
  await expect(
    comparison(page).getByRole("row", { name: /Supplier restock date/ }),
  ).toContainText("30 days later");

  const payloads: unknown[] = [];
  page.on("request", (sent) => {
    if (sent.url().endsWith("/api/simulations"))
      payloads.push(sent.postDataJSON());
  });
  await setDelay(page, 0);
  await run(page);
  expect(payloads).toEqual([{ supplier_id: "SUP-ALPHA", delay_days: 0 }]);
  await expect(
    comparison(page)
      .getByRole("row", { name: /Estimated penalty exposure/ })
      .getByRole("cell"),
  ).toHaveText(["£0", "£0", "£0"]);
  await expect(
    comparison(page)
      .getByRole("row", { name: /Affected orders/ })
      .getByRole("cell"),
  ).toHaveText(["0", "0", "0 orders"]);
  await expect(
    comparison(page)
      .getByRole("row", { name: /Supplier restock date/ })
      .getByRole("cell"),
  ).toHaveText(["27 Oct", "27 Oct", "No change"]);
  await expect(page.getByText("All orders remain on time.")).toBeVisible();
  await expect(explanation(page)).toContainText(
    "estimated penalty exposure stays at £0, while affected orders stay at 0",
  );
  await expect(explanation(page)).toContainText(
    "The backend recommends Accept the delay at £0",
  );
  await expect(explanation(page)).toContainText(
    "tied for the lowest returned total",
  );
});

for (const failedDelay of [0, 5]) {
  test(`a failed ${failedDelay === 0 ? "baseline" : "disrupted"} request preserves the pair and supports retry`, async ({
    page,
  }) => {
    await openWorkspace(page);
    await run(page);
    const before = await comparison(page).textContent();
    const previousExplanation = await explanation(page).textContent();
    await page.getByLabel("Supplier", { exact: true }).selectOption("SUP-BETA");
    const fail = async (route: Route) => {
      if (route.request().postDataJSON().delay_days === failedDelay) {
        await route.fulfill({
          status: 503,
          json: { detail: "Simulation temporarily unavailable" },
        });
      } else {
        await route.continue();
      }
    };
    await page.route("**/api/simulations", fail);
    await page.getByRole("button", { name: "Run simulation" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "Simulation temporarily unavailable",
    );
    await expect(
      page.getByText("Update failed · showing previous results"),
    ).toBeVisible();
    await expect(comparison(page)).toHaveText(before!);
    await expect(explanation(page)).toHaveText(previousExplanation!);
    await expect(
      page.getByRole("button", { name: "Run simulation" }),
    ).toBeEnabled();
    await page.unroute("**/api/simulations", fail);
    await run(page);
    await expect(comparison(page).getByRole("table")).toHaveAccessibleName(
      /SUP-BETA/,
    );
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.locator(".stale-notice")).toHaveCount(0);
  });
}

test("first-run failure displays an error without partial results and can recover", async ({
  page,
}) => {
  await openWorkspace(page);
  await page.route("**/api/simulations", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "Run simulation" }).click();
  await expect(page.getByRole("alert")).toContainText("Cannot reach the API");
  await expect(comparison(page)).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Financial impact summary" }),
  ).toHaveCount(0);
  await page.unroute("**/api/simulations");
  await run(page);
  await expect(comparison(page)).toBeVisible();
});

test("first run stays loading until the pair is complete", async ({ page }) => {
  await openWorkspace(page);
  const pending = gate();
  await page.route("**/api/simulations", async (route) => {
    await pending.promise;
    await route.continue();
  });
  try {
    await page.getByRole("button", { name: "Run simulation" }).click();
    await expect(
      page.getByRole("heading", { name: "Comparing baseline and disruption…" }),
    ).toBeVisible();
    await expect(comparison(page)).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Calculating…" }),
    ).toBeDisabled();
  } finally {
    pending.release();
  }
  await expect(comparison(page)).toBeVisible();
});

test("a short delay can move restock without causing late orders", async ({
  page,
  request,
}) => {
  await openWorkspace(page);
  await page.getByLabel("Supplier", { exact: true }).selectOption("SUP-GAMMA");
  await setDelay(page, 1);
  await run(page);
  const baseline = await simulate(request, "SUP-GAMMA", 0);
  const disrupted = await simulate(request, "SUP-GAMMA", 1);
  await expectExposure(page, baseline, disrupted);
  await expectExplanation(page, baseline, disrupted);
  await expect(explanation(page)).toContainText(
    "estimated penalty exposure stays at £0, while affected orders stay at 0",
  );
  await expect(
    comparison(page)
      .getByRole("row", { name: /Affected orders/ })
      .getByRole("cell"),
  ).toHaveText(["0", "0", "0 orders"]);
  await expect(
    comparison(page).getByRole("row", { name: /Supplier restock date/ }),
  ).toContainText("1 day later");
  await expect(page.getByText("All orders remain on time.")).toBeVisible();
});

test("comparison uses exact penny differences and calendar-day changes", async ({
  page,
}) => {
  await openWorkspace(page);
  const actual = await page.evaluate(async () => {
    // Load the same transformed module the application uses in the browser.
    const path = "/src/comparison.ts";
    const { exposureChange, deliveryChange } = await import(
      /* @vite-ignore */ path
    );
    return {
      pennies: exposureChange("0.20", "0.30"),
      decrease: exposureChange("15.10", "14.99"),
      unchanged: exposureChange("0.00", "0.00"),
      yearBoundary: deliveryChange("2026-12-31", "2027-01-01"),
      leapYear: deliveryChange("2028-02-28", "2028-03-01"),
      earlier: deliveryChange("2026-11-01", "2026-10-31"),
    };
  });
  expect(actual).toEqual({
    pennies: "0.10",
    decrease: "-0.11",
    unchanged: "0.00",
    yearBoundary: "1 day later",
    leapYear: "2 days later",
    earlier: "1 day earlier",
  });
});

for (const width of [1440, 768, 375, 320]) {
  test(`comparison remains accessible at ${width}px without page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await openWorkspace(page);
    await run(page);
    await expect(comparison(page)).toBeVisible();
    const layout = await page.evaluate(() => ({
      viewport: window.innerWidth,
      pageWidth: document.documentElement.scrollWidth,
      panelWidth: document
        .querySelector(".comparison-panel")!
        .getBoundingClientRect().width,
    }));
    expect(layout.pageWidth).toBeLessThanOrEqual(layout.viewport);
    expect(layout.panelWidth).toBeLessThanOrEqual(layout.viewport);
    await comparison(page).locator(".table-scroll").focus();
    await expect(comparison(page).locator(".table-scroll")).toBeFocused();
    if (width < 560) {
      await comparison(page).locator(".table-scroll").press("ArrowRight");
      await expect
        .poll(() =>
          comparison(page)
            .locator(".table-scroll")
            .evaluate((element) => element.scrollLeft),
        )
        .toBeGreaterThan(0);
      await comparison(page)
        .getByRole("columnheader", { name: "Change vs baseline" })
        .scrollIntoViewIfNeeded();
      await expect(
        comparison(page).getByRole("columnheader", {
          name: "Change vs baseline",
        }),
      ).toBeInViewport();
    }
    await page.screenshot({
      path: test.info().outputPath(`comparison-${width}.png`),
      fullPage: true,
    });
  });
}
