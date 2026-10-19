import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Return the folder a global `npm install -g` of the package lives in, or null when the prefix is unknown.
 *
 * npm passes its global prefix to the programs it starts as
 * `npm_config_global_prefix`. On Windows the default prefix is `%APPDATA%\npm`.
 *
 * @param {string} packageName
 * @param {Record<string, string|undefined>} environment
 * @param {string} platform The Node platform name.
 * @returns {string|null}
 */
export function globalPackageDirectory(packageName, environment, platform) {
    const windowsDefaultPrefix = platform === 'win32' && environment.APPDATA ? join(environment.APPDATA, 'npm') : null;
    const prefix = environment.npm_config_global_prefix || environment.npm_config_prefix || windowsDefaultPrefix;
    if (!prefix) return null;
    return platform === 'win32'
        ? join(prefix, 'node_modules', packageName)
        : join(prefix, 'lib', 'node_modules', packageName);
}

function samePath(firstPath, secondPath) {
    try {
        return realpathSync(firstPath).toLowerCase() === realpathSync(secondPath).toLowerCase();
    } catch {
        return false;
    }
}

/**
 * Find a global install of the package at another version than the one running.
 *
 * `npx <package>` with no version runs a global copy when one is on PATH, so
 * an old global copy runs instead of the newest release, and its update pass
 * prunes files that newer installs left for Codex and Cursor.
 *
 * @param {object} options
 * @param {string} options.packageName
 * @param {string} options.packageRoot The folder of the copy that is running.
 * @param {string} options.packageVersion The running version.
 * @param {Record<string, string|undefined>} [options.environment]
 * @param {string} [options.platform]
 * @returns {{directory: string, version: string}|null}
 */
export function findShadowingGlobalInstall(options) {
    const environment = options.environment ?? process.env;
    const directory = globalPackageDirectory(options.packageName, environment, options.platform ?? process.platform);
    if (!directory) return null;
    const manifestPath = join(directory, 'package.json');
    if (!existsSync(manifestPath) || samePath(directory, options.packageRoot)) return null;
    let version;
    try {
        version = JSON.parse(readFileSync(manifestPath, 'utf8')).version;
    } catch {
        return null;
    }
    if (!version || version === options.packageVersion) return null;
    return { directory, version };
}

/**
 * Say what the global copy does and the exact commands that fix it.
 *
 * @param {string} packageName
 * @param {{directory: string, version: string}} shadow
 * @param {string} packageVersion The running version.
 * @returns {string}
 */
export function shadowingGlobalAdvice(packageName, shadow, packageVersion) {
    return `A global ${packageName} ${shadow.version} is installed at ${shadow.directory}. `
        + `\`npx ${packageName}\` without a version runs that copy instead of ${packageVersion}. `
        + `Remove it with \`npm uninstall -g ${packageName}\`, or update it with \`npm install -g ${packageName}@latest\`.`;
}
