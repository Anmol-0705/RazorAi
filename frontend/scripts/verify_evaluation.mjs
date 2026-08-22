import { chromium } from "playwright-core";

const CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = "http://localhost:5173";
const consoleErrors = [];

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const page = await browser.newPage();
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

await page.goto(`${BASE}/evaluation`, { waitUntil: "networkidle" });
await page.waitForTimeout(300);
console.log("--- Evaluation page (before run) ---");
console.log((await page.locator("body").innerText()).slice(0, 500));

await page.getByRole("button", { name: "Run Evaluation" }).click();
await page.waitForTimeout(4000);
console.log("--- Evaluation page (after run) ---");
console.log(await page.locator("body").innerText());

await page.getByRole("button", { name: "Run Stress Evaluation" }).click();
await page.waitForTimeout(4000);
const stressBodyText = await page.locator("body").innerText();
console.log("--- Evaluation page (after stress run) ---");
console.log(stressBodyText);

// Regression check: the stress auto-resolution stat must use the
// clarified label, never the old "Auto-Resolution Precision" wording,
// and the "zero Controller Actions executed" note must be present.
// StatCard labels render with CSS text-transform: uppercase, which
// innerText() reflects -- compare case-insensitively.
const lowerBody = stressBodyText.toLowerCase();
const hasClarifiedLabel = lowerBody.includes("auto-resolution classification agreement");
const hasOldLabel = lowerBody.includes("auto-resolution precision");
const hasExplanatoryNote = lowerBody.includes("no controller actions are executed during this benchmark");

console.log("=== STRESS METRIC WORDING CHECK ===");
console.log("has clarified label 'Auto-Resolution Classification Agreement':", hasClarifiedLabel);
console.log("has stale label 'Auto-Resolution Precision':", hasOldLabel);
console.log("has explanatory note about zero Controller Actions:", hasExplanatoryNote);

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");
await browser.close();

if (!hasClarifiedLabel || hasOldLabel || !hasExplanatoryNote || consoleErrors.length) {
  process.exit(1);
}
