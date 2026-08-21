import { chromium } from "playwright-core";

const CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = "http://localhost:5173";
const API = "http://localhost:8000";

const consoleErrors = [];

// Find a pending exception via the real API (same one the UI calls).
const runs = await (await fetch(`${API}/reconciliation/runs?limit=1`)).json();
const runId = runs[0].id ?? runs[0].run_id;
const exceptions = await (
  await fetch(`${API}/exceptions?run_id=${runId}&status=pending&limit=1`)
).json();
if (!exceptions.length) throw new Error("no pending exception found to test review actions on");
const exceptionId = exceptions[0].id;
console.log("Testing review workflow on exception:", exceptionId, exceptions[0].exception_type);

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const page = await browser.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

await page.goto(`${BASE}/exceptions/${exceptionId}`, { waitUntil: "networkidle" });
await page.waitForTimeout(400);

const reviewSection = page.locator("section", { hasText: "Human review" });
console.log("--- Before actions ---");
console.log(await reviewSection.innerText());

await reviewSection.getByRole("button", { name: "Start Review", exact: true }).click();
await page.waitForTimeout(700);
console.log("--- After Start Review ---");
console.log(await reviewSection.innerText());

await reviewSection.getByRole("button", { name: "Approve", exact: true }).click();
await page.waitForTimeout(300);
const dialog = page.locator(".fixed.inset-0");
console.log("dialog visible:", await dialog.isVisible());
await dialog.getByRole("button", { name: "Approve", exact: true }).click();
await page.waitForTimeout(800);
console.log("--- After Approve ---");
console.log(await reviewSection.innerText());

// Reload and confirm the persisted state survives a fresh fetch.
await page.reload({ waitUntil: "networkidle" });
await page.waitForTimeout(400);
console.log("--- After reload (persisted state check) ---");
console.log(await reviewSection.innerText());

const auditSection = page.locator("section", { hasText: "Audit history" });
console.log("--- Audit history ---");
console.log(await auditSection.innerText());

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");

await browser.close();
