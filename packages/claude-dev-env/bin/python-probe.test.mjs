import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { execSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { detectPython } from './install.mjs';
import { pythonExecutableProbeCommand } from './python-probe.mjs';

const SHADOWED_STANDARD_LIBRARY_MODULES = ['linecache.py', 'encodings.py', 'site.py', 'os.py'];

test('the interpreter path probe ignores modules in the current directory', () => {
    const candidateCommand = detectPython();
    assert.ok(candidateCommand, 'a Python 3 interpreter is needed for this test');
    const shadowDirectory = mkdtempSync(join(tmpdir(), 'cde-python-probe-'));
    try {
        for (const moduleFileName of SHADOWED_STANDARD_LIBRARY_MODULES) {
            writeFileSync(join(shadowDirectory, moduleFileName), 'raise SystemExit("shadow module imported")\n');
        }
        const printedPath = execSync(pythonExecutableProbeCommand(candidateCommand), {
            cwd: shadowDirectory,
            encoding: 'utf8',
            stdio: ['pipe', 'pipe', 'pipe'],
        }).trim();
        assert.ok(printedPath.length > 0);
        assert.doesNotMatch(printedPath, /shadow module imported/);
    } finally {
        rmSync(shadowDirectory, { recursive: true, force: true });
    }
});

test('the interpreter path probe runs Python in isolated mode', () => {
    assert.equal(
        pythonExecutableProbeCommand('py -3'),
        'py -3 -I -c "import sys; print(sys.executable)"',
    );
});
