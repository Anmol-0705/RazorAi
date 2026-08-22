import { chromium } from "playwright-core";

const CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = "http://localhost:5173";
const API = "http://localhost:8000";

const exceptions = await (await fetch(`${API}/exceptions?exception_type=fee_mismatch&limit=1`)).json();
if (!exceptions.length) throw new Error("no fee_mismatch exception found to test on");
const exceptionId = exceptions[0].id;
console.log("Testing exception:", exceptionId);

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true });
const page = await browser.newPage();
const pageErrors = [];
page.on("pageerror", (err) => pageErrors.push(err.message));
page.on("console", (msg) => {
  if (msg.type() === "error") pageErrors.push(`console.error: ${msg.text()}`);
});

await page.route(`${API}/exceptions/**`, async (route) => {
  const response = await route.fetch();
  const json = await response.json();
  if (json.exception) {
    delete json.action_executions;
    delete json.controller_action;
  }
  await route.fulfill({ response, json });
});

await page.goto(`${BASE}/exceptions/${encodeURIComponent(exceptionId)}`, { waitUntil: "networkidle" });
await page.waitForTimeout(500);

console.log("=== PAGE/CONSOLE ERRORS (old-backend-shape simulation) ===");
console.log(pageErrors.length ? pageErrors.join("\n") : "(none)");

const bodyText = await page.locator("body").innerText();
console.log("Human review section present:", bodyText.includes("Human review"));
console.log("Audit history section present:", bodyText.includes("Audit history"));
console.log("Controller Action section present:", bodyText.includes("Controller Action"));

await browser.close();
if (pageErrors.length) process.exit(1);
