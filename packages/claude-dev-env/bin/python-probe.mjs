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
