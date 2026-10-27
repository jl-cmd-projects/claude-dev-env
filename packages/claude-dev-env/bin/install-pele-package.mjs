import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, win32 } from 'node:path';
import { namesAnAbsentCommand, runHostCommand, singleLineDetail } from './install-pstack-plugin.mjs';

export const PELE_PACKAGE_NAME = 'pele';
export const PELE_PACKAGE_OPT_OUT_FLAG = '--no-pele';
export const PELE_PACKAGE_OPT_OUT_VARIABLE = 'CDE_INSTALL_PELE';
export const PELE_TOOLS_DIRECTORY_NAME = 'tools';
const PELE_HOST_PACKAGE_NAME = 'claude-dev-env-pele-host';
const NPM_COMMAND_TIMEOUT_MILLISECONDS = 120000;
const PELE_NPM_COMMAND = 'npm';
const WINDOWS_DEFAULT_PATHEXT = '.COM;.EXE;.BAT;.CMD';
const WINDOWS_SHIM_EXTENSIONS = ['.cmd', '.bat'];
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

function windowsVariable(environment, name) {
    const entry = Object.entries(environment).find(([key, value]) => key.toUpperCase() === name && value);
    return entry ? entry[1] : '';
}

/**
 * Name the npm executable to launch.
 *
 * `cmd.exe` gives the `npm.cmd` shim a bare command name for `%~dp0`, so the shim
 * resolves its Node folder against the working directory and cannot find npm. On
 * Windows the first npm that `PATH` and `PATHEXT` select is therefore launched by
 * absolute path when it is a `.cmd` or `.bat` shim. Any other npm, such as a
 * version manager's `npm.exe`, keeps the bare name and `cmd.exe` chooses it.
 *
 * @param {string} [platform] The platform to resolve for.
 * @param {Record<string, string|undefined>} [environment] Supplies `PATH` and `PATHEXT` in any casing.
 * @param {(candidate: string) => boolean} [fileExists] Tells whether a candidate file exists.
 * @returns {string} The absolute shim path, or the bare name `npm`.
 */
export function resolveNpmExecutable(platform = process.platform, environment = process.env, fileExists = existsSync) {
    if (platform !== 'win32') return 'npm';
    const directories = windowsVariable(environment, 'PATH')
        .split(';')
        .map(directory => directory.replace(/^"(.*)"$/, '$1'))
        .filter(directory => win32.isAbsolute(directory));
    const extensions = (windowsVariable(environment, 'PATHEXT') || WINDOWS_DEFAULT_PATHEXT)
        .split(';')
        .filter(Boolean)
        .map(extension => extension.toLowerCase());
    for (const directory of directories) {
        for (const extension of extensions) {
            const candidate = win32.join(directory, `${PELE_NPM_COMMAND}${extension}`);
            if (fileExists(candidate)) return WINDOWS_SHIM_EXTENSIONS.includes(extension) ? candidate : PELE_NPM_COMMAND;
        }
    }
    return PELE_NPM_COMMAND;
}

function runNpm(commandArguments, options = {}) {
    return runHostCommand(resolveNpmExecutable(), commandArguments, {
        cwd: options.cwd,
        timeoutMilliseconds: NPM_COMMAND_TIMEOUT_MILLISECONDS,
    });
}

function failureDetail(outcome, fallback) {
    const cause = outcome.error?.code === 'ETIMEDOUT'
        ? `timed out after ${NPM_COMMAND_TIMEOUT_MILLISECONDS} ms`
        : outcome.error?.message;
    return singleLineDetail([cause, outcome.stderr].filter(Boolean).join(' ') || fallback);
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
 * @param {{installDirectory: string, run?: (commandArguments: string[], options?: {cwd?: string}) => {status: number|null, stdout: string, stderr: string, error?: Error}}} options
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
        cwd: nearestExistingDirectory(installDirectory),
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
        ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--loglevel=error', `${PELE_PACKAGE_NAME}@${latestVersion}`],
        { cwd: installDirectory },
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
 * Delete the Pele install directory an earlier install created.
 *
 * @param {string} installDirectory The folder `installPelePackage` filled.
 * @returns {boolean} True when a folder was removed.
 */
export function removePelePackage(installDirectory) {
    if (!existsSync(installDirectory)) return false;
    rmSync(installDirectory, { recursive: true, force: true, maxRetries: PELE_REMOVAL_RETRIES });
    return true;
}
