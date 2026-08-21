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

async function goto(path, label) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  console.log(`--- ${label} (${path}) ---`);
}

await goto("/", "Dashboard (empty state)");
console.log(await page.locator("body").innerText());

// Generate a dataset and run reconciliation through the real UI controls.
await page.getByRole("button", { name: "100" }).click();
await page.getByRole("button", { name: "Generate demo dataset" }).click();
await page.waitForTimeout(1500);
console.log("after generate:", await page.locator("text=Generated dataset").first().innerText().catch(() => "(no success text found)"));

await page.getByRole("button", { name: "Run reconciliation" }).click();
await page.waitForTimeout(2500);
console.log("after run:", await page.locator("text=completed.").first().innerText().catch(() => "(no completion text found)"));

await page.waitForTimeout(500);
await page.reload({ waitUntil: "networkidle" });
await page.waitForTimeout(500);
console.log("--- Dashboard after run ---");
console.log(await page.locator("body").innerText());

await goto("/transactions", "Transactions");
console.log(await page.locator("table").first().innerText().catch(() => "(no table found)"));

await goto("/exceptions", "Exceptions");
const firstViewLink = page.getByRole("link", { name: "View" }).first();
const exceptionsBodyText = await page.locator("body").innerText();
console.log(exceptionsBodyText.slice(0, 800));

if (await firstViewLink.count()) {
  await firstViewLink.click();
  await page.waitForTimeout(600);
  console.log("--- Exception Detail ---");
  console.log(await page.locator("body").innerText());

  const startReview = page.getByRole("button", { name: "Start Review" });
  if (await startReview.isEnabled().catch(() => false)) {
    await startReview.click();
    await page.waitForTimeout(800);
    console.log("after start-review:", await page.locator("text=Start Review recorded").first().innerText().catch(() => "(no feedback text)"));
  }

  const approveBtn = page.getByRole("button", { name: "Approve" });
  await approveBtn.click();
  await page.waitForTimeout(300);
  const confirmBtn = page.getByRole("button", { name: "Approve" }).last();
  await confirmBtn.click();
  await page.waitForTimeout(800);
  console.log("--- After Approve ---");
  console.log(await page.locator("body").innerText());
}

await goto("/review", "Review Queue");
console.log(await page.locator("body").innerText());

await goto("/evaluation", "Evaluation placeholder");
console.log(await page.locator("body").innerText());

console.log("=== CONSOLE/PAGE ERRORS ===");
console.log(consoleErrors.length ? consoleErrors.join("\n") : "(none)");

await browser.close();
