import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { namesAnAbsentCommand, runHostCommand, singleLineDetail } from './install-pstack-plugin.mjs';

export const PELE_PACKAGE_NAME = 'pele';
export const PELE_PACKAGE_OPT_OUT_FLAG = '--no-pele';
export const PELE_PACKAGE_OPT_OUT_VARIABLE = 'CDE_INSTALL_PELE';
export const PELE_TOOLS_DIRECTORY_NAME = 'tools';
const PELE_HOST_PACKAGE_NAME = 'claude-dev-env-pele-host';
const NPM_COMMAND_TIMEOUT_MILLISECONDS = 120000;
const PELE_REMOVAL_RETRIES = 3;
const VERSION_PATTERN = /^(\d+)\.(\d+)\.(\d+)/;
const PLAIN_VERSION_PATTERN = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/;

export const PELE_PACKAGE_SPEC = Object.freeze({
    optOutFlag: PELE_PACKAGE_OPT_OUT_FLAG,
    optOutVariable: PELE_PACKAGE_OPT_OUT_VARIABLE,
});

/**
 * Name the folder one managed root keeps its Pele install in.
 *
 * @param {string} managedRoot The managed Claude root.
 * @returns {string} `<managedRoot>/tools/pele`.
 */
export function peleInstallDirectory(managedRoot) {
    return join(managedRoot, PELE_TOOLS_DIRECTORY_NAME, PELE_PACKAGE_NAME);
}

/**
 * Read the Pele version an install folder holds.
 *
 * @param {string} installDirectory The folder `npm install` ran in.
 * @returns {string|null} The version, or null when Pele is absent or its manifest is unreadable.
 */
export function installedPeleVersion(installDirectory) {
    const manifestPath = join(installDirectory, 'node_modules', PELE_PACKAGE_NAME, 'package.json');
    if (!existsSync(manifestPath)) return null;
    try {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
        return typeof manifest.version === 'string' ? manifest.version : null;
    } catch {
        return null;
    }
}

function versionParts(versionText) {
    const match = VERSION_PATTERN.exec(versionText ?? '');
    return match ? match.slice(1).map(Number) : null;
}

function isNewerVersion(candidateVersion, baselineVersion) {
    const candidateParts = versionParts(candidateVersion);
    const baselineParts = versionParts(baselineVersion);
    if (!candidateParts || !baselineParts) return candidateVersion !== baselineVersion;
    for (let index = 0; index < candidateParts.length; index += 1) {
        if (candidateParts[index] !== baselineParts[index]) return candidateParts[index] > baselineParts[index];
    }
    return false;
}

function nearestExistingDirectory(directory) {
    let candidate = directory;
    while (!existsSync(candidate) && dirname(candidate) !== candidate) candidate = dirname(candidate);
    return candidate;
}

function runNpm(commandArguments, options = {}) {
    return runHostCommand('npm', commandArguments, {
        cwd: options.workingDirectory ?? options.installDirectory,
        timeoutMilliseconds: NPM_COMMAND_TIMEOUT_MILLISECONDS,
    });
}

function failureDetail(outcome, fallback) {
    return singleLineDetail(outcome.error?.message || outcome.stderr || fallback);
}

function prepareInstallDirectory(installDirectory) {
    mkdirSync(installDirectory, { recursive: true });
    const hostManifestPath = join(installDirectory, 'package.json');
    if (!existsSync(hostManifestPath)) {
        writeFileSync(hostManifestPath, `${JSON.stringify({ name: PELE_HOST_PACKAGE_NAME, private: true }, null, 2)}\n`);
    }
}

/**
 * Install Pele from the npm registry, or move an older copy to the latest version.
 *
 * Pele is a JavaScript library, so it lands in a private folder under the managed
 * root instead of the global npm prefix. A newer local copy stays as it is. A
 * registry or install failure leaves any existing copy in place and reports a
 * warning, so the rest of the install still completes.
 *
 * @param {{installDirectory: string, run?: (commandArguments: string[], options?: {installDirectory?: string}) => {status: number|null, stdout: string, stderr: string, error?: Error}}} options
 *   The install folder and an optional npm runner.
 * @returns {{status: 'installed'|'updated'|'current'|'skipped'|'failed', installedVersion: string|null, previousVersion: string|null, warning: string|null}} The outcome.
 */
export function installPelePackage({ installDirectory, run = runNpm }) {
    const previousVersion = installedPeleVersion(installDirectory);
    const outcome = (status, installedVersion, warning = null) => ({
        status,
        installedVersion,
        previousVersion,
        warning,
    });
    const lookup = run(['view', PELE_PACKAGE_NAME, 'version'], {
        workingDirectory: nearestExistingDirectory(installDirectory),
    });
    if (namesAnAbsentCommand(lookup)) {
        return outcome('skipped', previousVersion, 'npm was not found on PATH');
    }
    const latestVersion = lookup.status === 0 ? lookup.stdout.trim() : '';
    if (!PLAIN_VERSION_PATTERN.test(latestVersion)) {
        const detail = lookup.status === 0
            ? `npm view ${PELE_PACKAGE_NAME} returned something that is not a version`
            : `npm view ${PELE_PACKAGE_NAME} failed: ${failureDetail(lookup, 'no version returned')}`;
        return previousVersion
            ? outcome('current', previousVersion, detail)
            : outcome('failed', null, detail);
    }
    if (previousVersion && !isNewerVersion(latestVersion, previousVersion)) {
        return outcome('current', previousVersion);
    }
    prepareInstallDirectory(installDirectory);
    const installation = run(
        ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--loglevel=error',`${PELE_PACKAGE_NAME}@${latestVersion}`],
        { installDirectory },
    );
    if (installation.status !== 0) {
        return outcome(
            'failed',
            previousVersion,
            `npm install ${PELE_PACKAGE_NAME}@${latestVersion} failed: ${failureDetail(installation, 'no output')}`,
        );
    }
    const installedVersion = installedPeleVersion(installDirectory);
    if (installedVersion !== latestVersion) {
        return outcome(
            'failed',
            installedVersion,
            `npm install finished but ${PELE_PACKAGE_NAME} ${latestVersion} is not in ${installDirectory}`,
        );
    }
    return outcome(previousVersion ? 'updated' : 'installed', installedVersion);
}

/**
 * Delete the Pele install folder an earlier install created.
 *
 * @param {string} installDirectory The folder `installPelePackage` filled.
 * @returns {boolean} True when a folder was removed.
 */
export function removePelePackage(installDirectory) {
    if (!existsSync(installDirectory)) return false;
    rmSync(installDirectory, { recursive: true, force: true, maxRetries: PELE_REMOVAL_RETRIES });
    return true;
}
