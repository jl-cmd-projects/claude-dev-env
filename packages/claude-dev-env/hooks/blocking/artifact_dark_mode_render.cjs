#!/usr/bin/env node
"use strict";

const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const MINIMUM_CONTRAST_RATIO = 4.5;
const MAXIMUM_DARK_PAGE_LUMINANCE = 0.2;
const MAXIMUM_REPORTED_TEXT_FAILURES = 8;
const TEXT_SNIPPET_LENGTH = 60;
const PAGE_LOAD_TIMEOUT_MILLISECONDS = 15000;
const RENDERER_MISSING_EXIT_CODE = 3;
const ALL_DARK_SIGNALS = [
  { name: "prefers-color-scheme: dark", colorScheme: "dark", dataTheme: null },
  { name: 'data-theme="dark"', colorScheme: "light", dataTheme: "dark" },
];

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (localError) {
    const globalRoot = childProcess.execSync("npm root -g", { encoding: "utf8" }).trim();
    return require(path.join(globalRoot, "playwright"));
  }
}

function measurePage([maximumDarkPageLuminance, minimumContrastRatio, snippetLength]) {
  const parseColor = (colorText) => {
    const channels = (colorText.match(/[\d.]+/g) || []).map(Number);
    return { red: channels[0] || 0, green: channels[1] || 0, blue: channels[2] || 0, alpha: channels.length > 3 ? channels[3] : 1 };
  };
  const channelLuminance = (channel) => {
    const scaled = channel / 255;
    return scaled <= 0.03928 ? scaled / 12.92 : Math.pow((scaled + 0.055) / 1.055, 2.4);
  };
  const luminance = (color) => 0.2126 * channelLuminance(color.red) + 0.7152 * channelLuminance(color.green) + 0.0722 * channelLuminance(color.blue);
  const contrastRatio = (first, second) => {
    const lighter = Math.max(luminance(first), luminance(second));
    const darker = Math.min(luminance(first), luminance(second));
    return (lighter + 0.05) / (darker + 0.05);
  };
  const canvasColor = { red: 255, green: 255, blue: 255, alpha: 1 };
  const effectiveBackground = (element) => {
    for (let current = element; current; current = current.parentElement) {
      const background = parseColor(getComputedStyle(current).backgroundColor);
      if (background.alpha > 0.5) {
        return background;
      }
    }
    return canvasColor;
  };
  const isVisible = (element) => {
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0 && box.width > 0 && box.height > 0;
  };
  const allFindings = [];
  const pageBackground = effectiveBackground(document.body);
  if (luminance(pageBackground) > maximumDarkPageLuminance) {
    allFindings.push(`the page background stays light (${getComputedStyle(document.body).backgroundColor} on body); give body an explicit background from the theme tokens`);
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seenElements = new Set();
  for (let textNode = walker.nextNode(); textNode; textNode = walker.nextNode()) {
    const element = textNode.parentElement;
    const text = textNode.textContent.trim();
    if (!text || !element || seenElements.has(element) || ["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT"].includes(element.tagName)) {
      continue;
    }
    seenElements.add(element);
    if (!isVisible(element)) {
      continue;
    }
    const foreground = parseColor(getComputedStyle(element).color);
    const background = effectiveBackground(element);
    const ratio = contrastRatio(foreground, background);
    if (ratio < minimumContrastRatio) {
      allFindings.push(`text "${text.slice(0, snippetLength)}" has contrast ${ratio.toFixed(2)}:1 (${getComputedStyle(element).color} on rgb(${background.red}, ${background.green}, ${background.blue}))`);
    }
  }
  return allFindings;
}

async function checkSignal(browser, pageHtml, darkSignal) {
  const page = await browser.newPage({ colorScheme: darkSignal.colorScheme });
  page.setDefaultTimeout(PAGE_LOAD_TIMEOUT_MILLISECONDS);
  try {
    await page.setContent(pageHtml, { waitUntil: "load", timeout: PAGE_LOAD_TIMEOUT_MILLISECONDS }).catch(() => undefined);
    if (darkSignal.dataTheme) {
      await page.evaluate((themeName) => document.documentElement.setAttribute("data-theme", themeName), darkSignal.dataTheme);
    }
    const allFindings = await page.evaluate(measurePage, [MAXIMUM_DARK_PAGE_LUMINANCE, MINIMUM_CONTRAST_RATIO, TEXT_SNIPPET_LENGTH]);
    return allFindings;
  } finally {
    await page.close();
  }
}

async function main() {
  const pagePath = process.argv[2];
  const pageHtml = fs.readFileSync(pagePath, "utf8");
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
  const report = {};
  try {
    for (const darkSignal of ALL_DARK_SIGNALS) {
      const allFindings = await checkSignal(browser, pageHtml, darkSignal);
      if (allFindings.length > 0) {
        report[darkSignal.name] = allFindings.slice(0, MAXIMUM_REPORTED_TEXT_FAILURES + 1);
      }
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(report));
  return 0;
}

main().then((exitCode) => process.exit(exitCode));
