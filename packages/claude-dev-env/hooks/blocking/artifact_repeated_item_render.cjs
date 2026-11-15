#!/usr/bin/env node
"use strict";

const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const LARGEST_ICON_SIDE_IN_PIXELS = 64;
const ITEM_NAME_LENGTH = 120;
const VIEWPORT_SIZE = { width: 1280, height: 900 };
const PAGE_LOAD_TIMEOUT_MILLISECONDS = 15000;
const IMAGE_SETTLE_TIMEOUT_MILLISECONDS = 3000;
const PAGE_ADDRESS = "https://artifact-page.invalid/";
const STAND_IN_IMAGE = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"/>';
const RENDERER_MISSING_EXIT_CODE = 3;

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (localError) {
    const globalRoot = childProcess.execSync("npm root -g", { encoding: "utf8" }).trim();
    return require(path.join(globalRoot, "playwright"));
  }
}

function countDrawnItems([largestIconSide, itemNameLength]) {
  const isDrawn = (element) => {
    if (!element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
      return false;
    }
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const isLargerThanAnIcon = (element) => {
    const box = element.getBoundingClientRect();
    return box.width > largestIconSide || box.height > largestIconSide;
  };
  const timesByKindAndItem = new Map();
  const countItem = (kind, item) => {
    const key = `${kind}\n${item}`;
    timesByKindAndItem.set(key, (timesByKindAndItem.get(key) || 0) + 1);
  };
  for (const image of document.querySelectorAll("img[src]")) {
    const source = image.getAttribute("src").trim();
    if (source && isDrawn(image) && isLargerThanAnIcon(image)) {
      countItem("image", source);
    }
  }
  for (const element of document.querySelectorAll("[data-item]")) {
    const itemKey = element.getAttribute("data-item").trim();
    if (itemKey && isDrawn(element)) {
      countItem("data-item", itemKey);
    }
  }
  const allRepeats = [];
  for (const [key, times] of timesByKindAndItem) {
    if (times > 1) {
      const [kind, item] = key.split("\n");
      allRepeats.push({ kind, item: item.slice(0, itemNameLength), times });
    }
  }
  return allRepeats.sort((first, second) => second.times - first.times);
}

function loadEveryImage(settleTimeout) {
  const allLoads = [...document.querySelectorAll("img[src]")].map((image) => {
    image.loading = "eager";
    return image.complete ? Promise.resolve() : new Promise((resolve) => {
      image.addEventListener("load", resolve, { once: true });
      image.addEventListener("error", resolve, { once: true });
    });
  });
  return Promise.race([Promise.all(allLoads), new Promise((resolve) => setTimeout(resolve, settleTimeout))]);
}

async function main() {
  const pageHtml = fs.readFileSync(process.argv[2], "utf8");
  let playwright;
  try {
    playwright = loadPlaywright();
  } catch (loadError) {
    process.stderr.write("Playwright is not installed; run: npm install -g playwright && npx playwright install chromium\n");
    return RENDERER_MISSING_EXIT_CODE;
  }
  let browser;
  try {
    browser = await playwright.chromium.launch();
  } catch (launchError) {
    process.stderr.write(`Chromium did not start for Playwright; run: npx playwright install chromium (${launchError.message.split("\n")[0]})\n`);
    return RENDERER_MISSING_EXIT_CODE;
  }
  try {
    const page = await browser.newPage({ viewport: VIEWPORT_SIZE });
    page.setDefaultTimeout(PAGE_LOAD_TIMEOUT_MILLISECONDS);
    await page.route("**/*", (route) => {
      const request = route.request();
      if (request.url() === PAGE_ADDRESS) {
        return route.fulfill({ contentType: "text/html; charset=utf-8", body: pageHtml });
      }
      if (request.resourceType() === "image") {
        return route.fulfill({ contentType: "image/svg+xml", body: STAND_IN_IMAGE });
      }
      return route.continue();
    });
    await page.goto(PAGE_ADDRESS, { waitUntil: "load", timeout: PAGE_LOAD_TIMEOUT_MILLISECONDS }).catch(() => undefined);
    await page.evaluate(loadEveryImage, IMAGE_SETTLE_TIMEOUT_MILLISECONDS).catch(() => undefined);
    const allRepeats = await page.evaluate(countDrawnItems, [LARGEST_ICON_SIDE_IN_PIXELS, ITEM_NAME_LENGTH]);
    process.stdout.write(JSON.stringify({ repeats: allRepeats }));
  } finally {
    await browser.close();
  }
  return 0;
}

main().then((exitCode) => process.exit(exitCode));
