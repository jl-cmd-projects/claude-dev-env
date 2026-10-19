import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { findShadowingGlobalInstall, globalPackageDirectory, shadowingGlobalAdvice } from './global-install-shadow.mjs';

function makeScratch(context) {
    const scratch = mkdtempSync(join(tmpdir(), 'cde-shadow-'));
    context.after(() => rmSync(scratch, { recursive: true, force: true }));
    return scratch;
}

function writeGlobalCopy(prefix, version) {
    const directory = join(prefix, 'node_modules', 'claude-dev-env');
    mkdirSync(directory, { recursive: true });
    writeFileSync(join(directory, 'package.json'), JSON.stringify({ name: 'claude-dev-env', version }));
    return directory;
}

test('the global folder comes from npm, or the Windows default prefix', () => {
    assert.equal(
        globalPackageDirectory('claude-dev-env', { npm_config_global_prefix: '/usr/local' }, 'linux'),
        join('/usr/local', 'lib', 'node_modules', 'claude-dev-env'),
    );
    assert.equal(
        globalPackageDirectory('claude-dev-env', { APPDATA: 'C:/Roaming' }, 'win32'),
        join('C:/Roaming', 'npm', 'node_modules', 'claude-dev-env'),
    );
    assert.equal(globalPackageDirectory('claude-dev-env', {}, 'linux'), null);
});

test('an older global copy is found and named with the commands that fix it', (context) => {
    const scratch = makeScratch(context);
    const directory = writeGlobalCopy(join(scratch, 'npm'), '8.35.1');
    const shadow = findShadowingGlobalInstall({
        packageName: 'claude-dev-env',
        packageRoot: join(scratch, 'npx-copy'),
        packageVersion: '8.89.0',
        environment: { APPDATA: scratch },
        platform: 'win32',
    });
    assert.deepEqual(shadow, { directory, version: '8.35.1' });
    const advice = shadowingGlobalAdvice('claude-dev-env', shadow, '8.89.0');
    assert.match(advice, /global claude-dev-env 8\.35\.1/);
    assert.match(advice, /npm uninstall -g claude-dev-env/);
});

test('a global copy at the running version, or the running copy itself, is not reported', (context) => {
    const scratch = makeScratch(context);
    const directory = writeGlobalCopy(join(scratch, 'npm'), '8.89.0');
    const options = { packageName: 'claude-dev-env', environment: { APPDATA: scratch }, platform: 'win32' };
    assert.equal(findShadowingGlobalInstall({ ...options, packageRoot: join(scratch, 'x'), packageVersion: '8.89.0' }), null);
    assert.equal(findShadowingGlobalInstall({ ...options, packageRoot: directory, packageVersion: '9.0.0' }), null);
    assert.equal(findShadowingGlobalInstall({ ...options, environment: {}, packageRoot: directory, packageVersion: '1' }), null);
});
