#!/usr/bin/env node
/**
 * Lints a visual-plan page with the parsers the browser runs, then inlines
 * visualplan.css and visualplan.js into one portable file.
 *
 *   node pack.mjs plan.html [-o out.html] [--lint-only] [--artifact] [--quiet]
 *
 * The inline and artifact steps adapt pack.mjs from html-plan by Thariq Shihipar (MIT).
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, dirname, basename, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const runtimeDirectory = dirname(fileURLToPath(import.meta.url));
createRequire(import.meta.url)('./visualplan.js');
const { lint } = globalThis.VisualPlan;

const USAGE = 'usage: node pack.mjs plan.html [-o out.html] [--lint-only] [--artifact] [--quiet]';
const commandLine = process.argv.slice(2);
const outFlagAt = commandLine.findIndex((token) => token === '-o' || token === '--out');
const inputPath = commandLine.find((token, index) => !token.startsWith('-') && (outFlagAt < 0 || index !== outFlagAt + 1));
if (!inputPath) { console.error(USAGE); process.exit(2); }
const isLintOnly = commandLine.includes('--lint-only');
const isQuiet = commandLine.includes('--quiet');
const isArtifact = commandLine.includes('--artifact');

const pagePath = resolve(inputPath);
const pageDirectory = dirname(pagePath);
const packedPath = resolve(outFlagAt >= 0 ? commandLine[outFlagAt + 1] : pagePath.replace(/\.html?$/i, '') + '.packed.html');
const source = readFileSync(pagePath, 'utf8');

const report = lint(source);
if (!isQuiet) {
  console.log(`\n${basename(pagePath)}`);
  report.warnings.forEach((message) => console.log(`  warning: ${message}`));
  report.errors.forEach((message) => console.log(`  error: ${message}`));
}
if (report.errors.length) {
  console.log(`\n${report.errors.length} error(s), ${report.warnings.length} warning(s). Fix the errors and run again.`);
  process.exit(1);
}
if (isLintOnly) {
  console.log(`lint clean${report.warnings.length ? `, ${report.warnings.length} warning(s)` : ''}`);
  process.exit(0);
}

const runtimeFile = (href, name) => {
  const besidePage = resolve(pageDirectory, href);
  return existsSync(besidePage) && basename(besidePage) === name ? besidePage : resolve(runtimeDirectory, name);
};
let packed = source
  .replace(/<link\b[^>]*href=["']([^"']*visualplan\.css)["'][^>]*>/i, (whole, href) => `<style data-visualplan>\n${readFileSync(runtimeFile(href, 'visualplan.css'), 'utf8')}\n</style>`)
  .replace(/<script\b[^>]*src=["']([^"']*visualplan\.js)["'][^>]*>\s*<\/script>/i, (whole, href) => `<script data-visualplan>\n${readFileSync(runtimeFile(href, 'visualplan.js'), 'utf8').replace(/<\/script/gi, '<\\/script')}\n</script>`);
if (!/<html\b[^>]*data-visualplan-packed/i.test(packed)) packed = packed.replace(/<html\b/i, '<html data-visualplan-packed');
writeFileSync(packedPath, packed);

const shown = (path) => relative(process.cwd(), path) || path;
if (isArtifact) {
  const artifact = packed
    .replace(/<!doctype[^>]*>\s*/i, '')
    .replace(/<\/?html\b[^>]*>\s*/gi, '')
    .replace(/<meta\b[^>]*charset[^>]*>\s*/i, '')
    .replace(/<\/?head\b[^>]*>\s*/gi, '')
    .replace(/<\/?body\b[^>]*>\s*/gi, '');
  const artifactPath = packedPath.replace(/(\.packed)?\.html?$/i, '.artifact.html');
  writeFileSync(artifactPath, artifact);
  console.log(`${shown(artifactPath)}  publish this one with the Artifact tool, with the db capability`);
}
console.log(`${shown(packedPath)}  ${(Buffer.byteLength(packed) / 1024).toFixed(0)} KB${report.warnings.length ? `, ${report.warnings.length} warning(s)` : ''}`);
