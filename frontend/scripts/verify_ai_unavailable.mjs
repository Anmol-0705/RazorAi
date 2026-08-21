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

await page.goto(`${BASE}/ai-controller`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "How much money is at risk?" }).click();
await page.waitForTimeout(1200);
console.log("--- AI Controller with no API key configured ---");
console.log(await page.locator("body").innerText());

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");
await browser.close();
