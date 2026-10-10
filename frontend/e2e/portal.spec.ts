import { expect, test } from "@playwright/test";

// Requires the full stack (docker compose up) with seeded demo data.
const EMAIL = process.env.E2E_EMAIL ?? "ciso@acme-fintech.example";
const PASSWORD = process.env.E2E_PASSWORD ?? "ChangeMe-Nexus-Demo-2025!";

test("unauthenticated users are redirected to login", async ({ page }) => {
  await page.goto("/security");
  await expect(page).toHaveURL(/\/login/);
});

test("login, navigate, generate and verify a signed report", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Identity").fill(EMAIL);
  await page.getByLabel("Passphrase").fill(PASSWORD);
  await page.getByRole("button", { name: /establish session/i }).click();
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByText("ShadowAPI_Guard").first()).toBeVisible();

  await page.getByRole("link", { name: /ContextRAG/ }).click();
  await expect(page.getByTestId("rag-detail")).toContainText("Source coordinates");

  await page.getByRole("link", { name: /Reports/ }).click();
  await page.getByRole("button", { name: /generate report/i }).click();
  await page.getByRole("button", { name: /verify/i }).first().click();
  await expect(page.getByText("signature valid").first()).toBeVisible();
  await expect(page.getByTestId("audit-table")).toContainText("report.generate");
});

test("rejects wrong credentials", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Identity").fill(EMAIL);
  await page.getByLabel("Passphrase").fill("definitely-wrong");
  await page.getByRole("button", { name: /establish session/i }).click();
  await expect(page.locator("#login-error")).toContainText(/invalid/i);
});
