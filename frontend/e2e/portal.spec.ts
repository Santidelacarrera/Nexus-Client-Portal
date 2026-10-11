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

  await page.getByRole("button", { name: "Sign out", exact: true }).click();
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

// RFC 6238 TOTP, enough to drive the authenticator in tests
import { createHmac } from "crypto";
function totp(secretB32: string, offset = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secretB32.replace(/=+$/, "")) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offset));
  const h = createHmac("sha1", key).update(counter).digest();
  const o = h[h.length - 1] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000)).padStart(6, "0");
}

test("MFA: enrol, login requires second factor, recovery code, disable", async ({ page }) => {
  const email = "analyst@helix-health.example";
  const signIn = async () => {
    await page.goto("/login");
    await page.getByLabel("Identity").fill(email);
    await page.getByLabel("Passphrase").fill(PASSWORD);
    await page.getByRole("button", { name: /establish session/i }).click();
  };
  await signIn();
  await page.waitForURL(/overview/);
  await page.goto("/account");
  await page.getByRole("button", { name: "Enable MFA" }).click();
  const secret = (await page.getByTestId("mfa-secret").textContent())!.trim();
  await page.getByLabel("6-digit code").fill(totp(secret));
  await page.getByRole("button", { name: /confirm/i }).click();
  await expect(page.getByTestId("recovery-codes")).toBeVisible();
  const recovery = await page.getByTestId("recovery-codes").locator("li").allTextContents();
  expect(recovery).toHaveLength(8);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();

  // password alone is not enough; wrong code is rejected; next-step TOTP is accepted
  await signIn();
  await expect(page.getByLabel(/authenticator or recovery code/i)).toBeVisible();
  await page.getByLabel(/authenticator or recovery code/i).fill("000000");
  await page.getByRole("button", { name: /verify second factor/i }).click();
  await expect(page.locator("#login-error")).toContainText(/invalid/i);
  await page.getByLabel(/authenticator or recovery code/i).fill(totp(secret, 1));
  await page.getByRole("button", { name: /verify second factor/i }).click();
  await page.waitForURL(/overview/);

  // disable using a recovery code (leaves the demo account clean)
  await page.goto("/account");
  await page.getByLabel(/authenticator or recovery code/i).fill(recovery[0]);
  await page.getByRole("button", { name: "Disable MFA" }).click();
  await expect(page.getByRole("button", { name: "Enable MFA" })).toBeVisible();
});

test("change password ends all sessions; new password works", async ({ page, browser }) => {
  const email = "analyst@acme-fintech.example";
  const next = "Rotated-Passphrase-2026";
  const login = async (p: typeof page, pw: string) => {
    await p.goto("/login");
    await p.getByLabel("Identity").fill(email);
    await p.getByLabel("Passphrase").fill(pw);
    await p.getByRole("button", { name: /establish session/i }).click();
  };
  const other = await (await browser.newContext()).newPage(); // a second device
  await login(other, PASSWORD);
  await other.waitForURL(/overview/);
  await login(page, PASSWORD);
  await page.waitForURL(/overview/);
  await page.goto("/account");
  await page.getByLabel("Current password").fill(PASSWORD);
  await page.getByLabel("New password (12+ characters)").fill(next);
  await page.getByLabel("Confirm new password").fill(next);
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page).toHaveURL(/login/);
  await other.goto("/security"); // the other device's session was revoked server-side
  await expect(other).toHaveURL(/login/);
  await login(page, next);
  await page.waitForURL(/overview/);
  // restore the demo password through the same UI path is blocked by policy; leave rotated and sign out everywhere
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out everywhere" }).click();
  await expect(page).toHaveURL(/login/);
});

// Needs the API started with MFA_REQUIRED_ROLES='["viewer"]' (run in a separate pass).
test("MFA policy: confined role is sent to enrolment, then unlocked", async ({ page }) => {
  test.skip(!process.env.E2E_MFA_REQUIRED, "set E2E_MFA_REQUIRED=1 with MFA_REQUIRED_ROLES=[\"viewer\"]");
  await page.goto("/login");
  await page.getByLabel("Identity").fill("viewer@acme-fintech.example");
  await page.getByLabel("Passphrase").fill(PASSWORD);
  await page.getByRole("button", { name: /establish session/i }).click();
  await page.waitForURL(/\/account/); // login lands on /overview, which bounces a confined role to enrolment
  await page.goto("/security"); // any other data page bounces too
  await expect(page).toHaveURL(/\/account/);
  await expect(page.getByTestId("mfa-required-banner")).toBeVisible();
  await page.getByRole("button", { name: "Enable MFA" }).click();
  const secret = (await page.getByTestId("mfa-secret").textContent())!.trim();
  await page.getByLabel("6-digit code").fill(totp(secret));
  await page.getByRole("button", { name: /confirm/i }).click();
  await expect(page.getByTestId("recovery-codes")).toBeVisible();
  await page.goto("/security");
  await expect(page.getByTestId("findings-table")).toBeVisible();
});

// Needs the full 3-service stack (scripts/e2e/run_stack.sh) — run with E2E_ASK=1.
test("ask: released answer with authorised sources; hostile document is vetoed", async ({ page }) => {
  test.skip(!process.env.E2E_ASK, "set E2E_ASK=1 with the stack from scripts/e2e/run_stack.sh");
  await page.goto("/login");
  await page.getByLabel("Identity").fill("ciso@acme-fintech.example");
  await page.getByLabel("Passphrase").fill(PASSWORD);
  await page.getByRole("button", { name: /establish session/i }).click();
  await page.waitForURL(/overview/);
  await page.getByRole("link", { name: /Ask · Committee/ }).click();

  await page.getByLabel("Question").fill("¿Cuánto tiempo se conservan los registros de auditoría?");
  await page.getByRole("button", { name: /^ask$/i }).click();
  await expect(page.getByTestId("outcome")).toContainText("Released");
  await expect(page.getByTestId("answer")).toContainText("7 años");
  for (const a of ["hallucination_critic", "tenant_security_auditor", "coherence_validator"]) await expect(page.getByTestId(`vote-${a}`)).toContainText("approve");
  await expect(page.getByTestId("sources")).toContainText("politica_retencion.md");

  await page.getByLabel("Question").fill("¿Cuántos días de vacaciones tiene el personal?");
  await page.getByRole("button", { name: /^ask$/i }).click();
  await expect(page.getByTestId("outcome")).toContainText("Blocked");
  await expect(page.getByTestId("reasons")).toContainText("tenant_security_veto");
  await expect(page.getByTestId("answer")).toHaveCount(0);
  await expect(page.getByTestId("sources")).toHaveCount(0);
  await expect(page.getByTestId("ask-history")).toContainText("blocked");
  await page.screenshot({ path: "/tmp/claude-0/ask-blocked.png", fullPage: false });
});
