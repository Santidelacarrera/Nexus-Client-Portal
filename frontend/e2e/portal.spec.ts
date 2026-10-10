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

test("triage a finding, export CSV, and logout revokes the session", async ({ page, context }) => {
  await page.goto("/login");
  await page.getByLabel("Identity").fill(EMAIL);
  await page.getByLabel("Passphrase").fill(PASSWORD);
  await page.getByRole("button", { name: /establish session/i }).click();
  await page.waitForURL(/overview/);
  const stolen = (await context.cookies()).find((c) => c.name === "nexus_session")!.value;

  await page.goto("/security");
  await page.getByTestId("findings-table").locator("tbody tr").first().click();
  await page.getByRole("button", { name: "resolved", exact: true }).click();
  await expect(page.getByTestId("findings-table")).toBeVisible();
  const csv = await page.request.get("/api/backend/security/findings.csv");
  expect(csv.status()).toBe(200);
  expect(csv.headers()["content-type"]).toContain("text/csv");

  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page).toHaveURL(/login/);
  // The old bearer token must be dead server-side, not merely forgotten by the browser.
  const replay = await page.request.get("http://localhost:8000/api/v1/overview", { headers: { Authorization: `Bearer ${stolen}` } });
  expect(replay.status()).toBe(401);
});

test("session refresh rotates the cookie and keeps the user signed in", async ({ page, context }) => {
  await page.goto("/login");
  await page.getByLabel("Identity").fill(EMAIL);
  await page.getByLabel("Passphrase").fill(PASSWORD);
  await page.getByRole("button", { name: /establish session/i }).click();
  await page.waitForURL(/overview/);
  const before = (await context.cookies()).find((c) => c.name === "nexus_session")!.value;
  const r = await page.request.post("/api/session/refresh", { headers: { Origin: "http://localhost:3000" } });
  expect(r.status()).toBe(200);
  const after = (await context.cookies()).find((c) => c.name === "nexus_session")!.value;
  expect(after).not.toBe(before);
  await page.goto("/security");
  await expect(page.getByTestId("findings-table")).toBeVisible();
});
