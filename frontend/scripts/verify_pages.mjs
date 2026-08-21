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

for (const path of ["/review", "/evaluation", "/transactions", "/"]) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  console.log(`--- ${path} ---`);
  console.log((await page.locator("body").innerText()).slice(0, 500));
}

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");
await browser.close();
