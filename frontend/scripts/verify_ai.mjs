import { chromium } from "playwright-core";

const CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = "http://localhost:5173";
const API = "http://localhost:8000";
const consoleErrors = [];

// Ensure a run exists.
await fetch(`${API}/datasets/demo`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ seed: 42, num_records: 100 }),
});
const runResp = await (
  await fetch(`${API}/reconciliation/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: "demo-seed42-n100" }),
  })
).json();
const runId = runResp.run_id;
const exceptions = await (
  await fetch(`${API}/exceptions?run_id=${runId}&exception_type=amount_mismatch&limit=1`)
).json();
const exceptionId = exceptions[0].id;

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const page = await browser.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

// --- AI Controller page ---
await page.goto(`${BASE}/ai-controller`, { waitUntil: "networkidle" });
await page.waitForTimeout(300);
console.log("--- AI Controller (loaded) ---");
console.log((await page.locator("body").innerText()).slice(0, 400));

await page.getByRole("button", { name: "How much money is at risk?" }).click();
await page.waitForTimeout(1500);
console.log("--- AI Controller (after asking) ---");
console.log(await page.locator("body").innerText());

// --- Exception Detail: Explain with AI ---
await page.goto(`${BASE}/exceptions/${exceptionId}`, { waitUntil: "networkidle" });
await page.waitForTimeout(300);
await page.getByRole("button", { name: "Explain with AI" }).click();
await page.waitForTimeout(1200);
console.log("--- Exception Detail after Explain with AI ---");
const aiSection = page.locator("section", { hasText: "AI explanation" });
console.log(await aiSection.innerText());

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");
await browser.close();
