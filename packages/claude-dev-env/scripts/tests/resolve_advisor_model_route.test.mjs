import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(new URL('../resolve_advisor_model_route.mjs', import.meta.url));

function runBridge(input) {
    return spawnSync(process.execPath, [scriptPath], {
        input,
        encoding: 'utf8',
    });
}

test('advisor bridge uses the trusted advisor registration', () => {
    const result = runBridge(JSON.stringify({ model: 'Sol', reasoning_effort: 'high' }));
    assert.equal(result.status, 0);
    assert.deepEqual(JSON.parse(result.stdout).selected, {
        model: 'gpt-6.2-sol',
        effort: 'high',
    });
});

test('advisor bridge selects Sol at xhigh when the caller names no model or effort', () => {
    const result = runBridge(JSON.stringify({}));
    assert.equal(result.status, 0);
    assert.deepEqual(JSON.parse(result.stdout).selected, {
        model: 'gpt-6.2-sol',
        effort: 'xhigh',
    });
});

test('advisor bridge sends an Astra request to Sol at xhigh', () => {
    for (const reasoning_effort of ['low', 'medium', 'high', 'xhigh', 'max']) {
        const result = runBridge(JSON.stringify({ model: 'Astra', reasoning_effort }));
        assert.equal(result.status, 0);
        assert.deepEqual(JSON.parse(result.stdout).selected, {
            model: 'gpt-6.2-sol',
            effort: 'xhigh',
        });
    }
});

test('advisor bridge blocks malformed JSON', () => {
    const result = runBridge('{');
    assert.equal(result.status, 1);
    assert.deepEqual(JSON.parse(result.stdout), {
        status: 'blocked',
        diagnostic: 'advisor route input is not valid JSON',
    });
});

test('advisor bridge blocks non-object input', () => {
    const result = runBridge('[]');
    assert.equal(result.status, 1);
    assert.deepEqual(JSON.parse(result.stdout), {
        status: 'blocked',
        diagnostic: 'advisor route input must be an object',
    });
});

test('advisor bridge blocks invalid policy paths', () => {
    for (const policyPath of [null, {}, '']) {
        const bridgeRun = runBridge(JSON.stringify({ policyPath }));
        assert.equal(bridgeRun.status, 1);
        assert.deepEqual(JSON.parse(bridgeRun.stdout), {
            status: 'blocked',
            diagnostic: 'advisor route policyPath must be a non-empty string',
        });
    }
});
