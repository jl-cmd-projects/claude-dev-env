#!/usr/bin/env node
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { applyCodexSolSettings, SOL_PROMPT_DIRECTORY_NAME, SOL_PROMPT_FILE_NAME } from './codex-trimmed-sol.mjs';
import { resolveInstallRoot } from './resolve-install-root.mjs';

const packageRoot = fileURLToPath(new URL('..', import.meta.url));
const resolution = resolveInstallRoot();
const changed = applyCodexSolSettings(
    resolution.codexHomeDirectory,
    join(packageRoot, SOL_PROMPT_DIRECTORY_NAME, SOL_PROMPT_FILE_NAME),
);
for (const eachPath of changed) process.stdout.write(`${eachPath}\n`);
