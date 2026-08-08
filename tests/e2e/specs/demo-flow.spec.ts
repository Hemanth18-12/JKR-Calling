import { expect, test } from "@playwright/test";

/**
 * Walks the UI-navigable portion of the spec §33 demo flow: signup → create
 * workspace → create + publish-ready an agent → add approved knowledge →
 * add a contact with consent → create a campaign → dry-run it and see the
 * safety gate's per-contact result. Stops short of waiting for the async
 * dialer loop to actually place and complete a mock call and book an
 * appointment — that's proven end-to-end by `scripts/run_demo.py`
 * (`make demo`), which is faster and more reliable to assert against than a
 * UI poll loop with no visible progress indicator to wait on.
 */

test("signup through campaign dry-run", async ({ page }) => {
  const suffix = Date.now().toString().slice(-8);
  const email = `e2e-${suffix}@example.com`;

  await test.step("sign up", async () => {
    await page.goto("/signup");
    await page.getByLabel("Full name").fill("E2E Test User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("CorrectHorse123!");
    await page.getByRole("button", { name: /create account|sign up/i }).click();
    await page.waitForURL(/\/app\//, { timeout: 15_000 });
  });

  await test.step("create a workspace", async () => {
    await page.getByLabel("Business name").fill(`E2E Biz ${suffix}`);
    await page.getByLabel("Workspace URL slug").fill(`e2e-biz-${suffix}`);
    await page.getByRole("button", { name: /create workspace/i }).click();
    // Confirms the empty-state "create your first workspace" screen is gone
    // and the real dashboard (with its KPI cards) has taken its place — more
    // reliable than matching the workspace name, which also appears (hidden)
    // in the header's <select> workspace switcher.
    await expect(page.getByText("Total calls")).toBeVisible({ timeout: 10_000 });
  });

  await test.step("create an agent", async () => {
    await page.goto("/app/agents/new");
    await page.getByLabel("Agent name").fill("E2E Receptionist");
    await page.getByLabel("Business identity (spoken in greeting)").fill(`E2E Biz ${suffix}`);
    await page.getByRole("button", { name: /create agent/i }).click();
    await page.waitForURL(/\/app\/agents\/[0-9a-f-]+$/, { timeout: 10_000 });
    await expect(page.getByText("AI disclosure")).toBeVisible();

    // Campaigns can only use a published agent version — see
    // components/new-campaign-form.tsx's published_version_id filter.
    await page.getByRole("button", { name: /publish this version/i }).click();
    await expect(page.getByText(/^published$/i).first()).toBeVisible({ timeout: 10_000 });
  });

  await test.step("add approved knowledge", async () => {
    await page.goto("/app/knowledge/documents");
    await page.getByLabel("Title").fill("E2E FAQ");
    await page.getByLabel("Content").fill("Our clinic is open Monday to Saturday, 9 AM to 8 PM.");
    await page.getByRole("button", { name: /add & process/i }).click();
    await expect(page.getByText("E2E FAQ")).toBeVisible({ timeout: 10_000 });
  });

  await test.step("add a contact and record consent", async () => {
    await page.goto("/app/contacts");
    await page.getByLabel("Full name").fill("E2E Contact");
    // Two "Phone" fields exist on this page (add-contact + suppress-a-number
    // forms); the add-contact one is first in DOM order.
    await page.getByLabel("Phone").first().fill(`98765${suffix.slice(-5)}`);
    await page.getByRole("button", { name: /add contact/i }).click();
    await expect(page.getByText("E2E Contact")).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: /record consent/i }).click();
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText("granted")).toBeVisible({ timeout: 10_000 });
  });

  await test.step("create a campaign and add the contact", async () => {
    await page.goto("/app/campaigns/new");
    await page.getByLabel("Campaign name").fill(`E2E Campaign ${suffix}`);
    await page.getByRole("button", { name: /create campaign/i }).click();
    await page.waitForURL(/\/app\/campaigns\/[0-9a-f-]+$/, { timeout: 10_000 });

    await page.getByRole("checkbox").first().check();
    await page.getByRole("button", { name: /^add \d+ selected$/i }).click();
    await expect(page.getByText("E2E Contact")).toBeVisible({ timeout: 10_000 });
  });

  await test.step("dry-run the safety gate", async () => {
    await page.getByRole("button", { name: /run dry-run/i }).click();
    // The real safety gate result — "would dispatch" if run inside calling
    // hours, "blocked: <check>" (most likely calling_hours, outside a
    // typical CI run's wall-clock) otherwise. Either is a correct, real
    // result — this test only exercises the safety gate is live and
    // rendering, not any particular check outcome.
    await expect(page.getByText(/would dispatch|blocked/i).first()).toBeVisible({ timeout: 10_000 });
  });
});
