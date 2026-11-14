import { spawnSync } from 'node:child_process';

export const MINIMUM_PYTHON_VERSION = '3.11';

/**
 * Reports whether a `--version` line names a Python at or above the package floor.
 *
 * The floor is MINIMUM_PYTHON_VERSION, the `requires-python` bound of the package.
 * Major and minor compare as numbers, so 3.9 sits below 3.11::
 *
 *     'Python 3.11.0'  -> true
 *     'Python 3.9.18'  -> false
 *     'Python 2.7.18'  -> false
 *
 * @param {string} versionOutput The text a `python --version` probe printed.
 * @returns {boolean} True when the version is at or above the floor.
 */
export function pythonVersionMeetsFloor(versionOutput) {
    const versionMatch = /Python (\d+)\.(\d+)/.exec(versionOutput);
    if (!versionMatch) return false;
    const [floorMajor, floorMinor] = MINIMUM_PYTHON_VERSION.split('.').map(Number);
    const candidateMajor = Number(versionMatch[1]);
    const candidateMinor = Number(versionMatch[2]);
    if (candidateMajor !== floorMajor) return candidateMajor > floorMajor;
    return candidateMinor >= floorMinor;
}

/**
 * Reports whether a Python command starts and is at or above the package floor.
 *
 * The command runs as `<command> --version` with no shell. It passes when it
 * exits 0 and its standard output names a version at or above
 * MINIMUM_PYTHON_VERSION. A missing command fails.
 *
 * @param {string} commandName The interpreter command or path to probe.
 * @returns {boolean} True when the command meets the floor.
 */
export function pythonCommandMeetsFloor(commandName) {
    const versionRun = spawnSync(commandName, ['--version'], { encoding: 'utf8', shell: false });
    return versionRun.status === 0 && pythonVersionMeetsFloor(versionRun.stdout ?? '');
}

/**
 * Command line for the probe that asks a Python candidate for its absolute
 * interpreter path.
 *
 * `python -c` puts the current directory first on `sys.path`, and Python
 * lists that whole directory the first time it imports a module from disk.
 * When the installer runs from a large folder, such as a temp folder with
 * hundreds of thousands of entries, that listing can outlast the probe
 * timeout, so every candidate fails and the install stops with "No usable
 * Python 3 found". A module in that folder with a standard library name is
 * imported in place of the real one. `-I` (isolated mode, Python 3.4+) keeps
 * the current directory off `sys.path`, so the probe gives the same answer
 * from any folder.
 *
 * @param {string} candidateCommand A Python launcher command, such as `py -3`.
 * @returns {string} The shell command that prints the interpreter path.
 */
export function pythonExecutableProbeCommand(candidateCommand) {
    return `${candidateCommand} -I -c "import sys; print(sys.executable)"`;
}
