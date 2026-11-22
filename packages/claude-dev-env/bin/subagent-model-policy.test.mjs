import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
    defaultSubagentModelPolicyPath,
    loadSubagentModelPolicy,
    resolveSubagentModelRoute,
    routeSubagentToolInput,
    SubagentModelPolicyError,
    validateSubagentModelPolicy,
} from '../scripts/subagent_model_policy.mjs';

const PACKAGE_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const POLICY_SOURCE = defaultSubagentModelPolicyPath();

function route(request, options = {}) {
    return resolveSubagentModelRoute(request, options);
}

function advisorRoute(request, options = {}) {
    return route(request, {
        trustedSessionMetadata: {
            authorized: true,
            registeredAgentType: 'team-advisor',
        },
        ...options,
    });
}

const replacements = [
    [['Luna', 'low'], ['gpt-5.6-luna', 'high']],
    [['Luna', 'medium'], ['gpt-5.6-luna', 'high']],
    [['Sol', 'low'], ['gpt-5.6-luna', 'xhigh']],
    [['Sol', 'medium'], ['gpt-5.6-luna', 'max']],
    [['Terra', 'low'], ['gpt-5.6-luna', 'xhigh']],
    [['Terra', 'medium'], ['gpt-5.6-luna', 'xhigh']],
    [['Terra', 'high'], ['gpt-5.6-luna', 'xhigh']],
    [['Terra', 'xhigh'], ['gpt-5.6-luna', 'max']],
    [['Sol', 'max'], ['gpt-6.2-sol', 'xhigh']],
    [['Terra', 'max'], ['gpt-6.2-sol', 'xhigh']],
    [['Astra', 'low'], ['gpt-6.2-sol', 'xhigh']],
    [['Astra', 'medium'], ['gpt-6.2-sol', 'xhigh']],
    [['Astra', 'high'], ['gpt-6.2-sol', 'xhigh']],
    [['Astra', 'xhigh'], ['gpt-6.2-sol', 'xhigh']],
    [['Astra', 'max'], ['gpt-6.2-sol', 'xhigh']],
];

const ASTRA_MODEL_PATTERN = /astra/i;

function everyRoutableRequest(policy) {
    const allModelTokens = [
        ...Object.values(policy.modelByName).flatMap(model => model.aliases),
        ...policy.inheritanceAliases,
    ];
    const allEffortTokens = [...policy.effortNames, ...Object.keys(policy.efforts.aliases), null];
    const allRoleRequests = [
        { request: {}, routeFunction: route },
        ...[...policy.roleByAlias.entries()]
            .filter(([, role]) => role === 'worker')
            .map(([alias]) => ({ request: { agent_type: alias }, routeFunction: route })),
        ...[...policy.trustedAdvisorRoles].map(alias => ({
            request: { agent_type: alias },
            routeFunction: advisorRoute,
        })),
    ];
    const allRequests = [];
    for (const { request, routeFunction } of allRoleRequests) {
        for (const effort of allEffortTokens) {
            const effortField = effort === null ? {} : { reasoning_effort: effort };
            for (const model of [...allModelTokens, null]) {
                const modelField = model === null ? {} : { model };
                allRequests.push({
                    request: { ...request, ...modelField, ...effortField },
                    routeFunction,
                });
            }
        }
    }
    return allRequests;
}

test('the shipped policy parses and names native model ids', () => {
    const policy = loadSubagentModelPolicy();
    assert.equal(policy.modelByName.sol.id, 'gpt-6.2-sol');
    assert.equal(policy.modelByName.terra.id, 'gpt-5.6-terra');
    assert.equal(policy.modelByName.luna.id, 'gpt-5.6-luna');
    assert.deepEqual(policy.advisorDefault, { model: 'sol', effort: 'xhigh' });
});

test('the advisor default resolves to Sol at xhigh', () => {
    const result = advisorRoute({ agent_type: 'team-advisor' });
    assert.equal(result.status, 'remapped');
    assert.equal(result.role, 'advisor');
    assert.deepEqual(result.selected, { model: 'gpt-6.2-sol', effort: 'xhigh' });
});

test('a lead request at Sol xhigh keeps Sol at xhigh', () => {
    const aliasRoute = route({ model: 'Sol', reasoning_effort: 'xhigh' });
    assert.equal(aliasRoute.status, 'remapped');
    assert.deepEqual(aliasRoute.selected, { model: 'gpt-6.2-sol', effort: 'xhigh' });
    const nativeRoute = route({ model: 'gpt-6.2-sol', reasoning_effort: 'xhigh' });
    assert.equal(nativeRoute.status, 'pass');
    assert.deepEqual(nativeRoute.selected, { model: 'gpt-6.2-sol', effort: 'xhigh' });
});

test('a worker request at Sol high keeps Sol at high', () => {
    const aliasRoute = route({ agent_type: 'worker', model: 'Sol', reasoning_effort: 'high' });
    assert.equal(aliasRoute.role, 'worker');
    assert.deepEqual(aliasRoute.selected, { model: 'gpt-6.2-sol', effort: 'high' });
    const nativeRoute = route({ agent_type: 'worker', model: 'gpt-6.2-sol', reasoning_effort: 'high' });
    assert.equal(nativeRoute.status, 'pass');
    assert.deepEqual(nativeRoute.selected, { model: 'gpt-6.2-sol', effort: 'high' });
});

test('no request of any model, effort, or role resolves to an Astra id', () => {
    const policy = loadSubagentModelPolicy();
    const allRequests = everyRoutableRequest(policy);
    const allSelectedModels = [];
    for (const { request, routeFunction } of allRequests) {
        const result = routeFunction(request, { allowMissingEffort: true });
        if (result.selected?.model) allSelectedModels.push(result.selected.model);
        assert.doesNotMatch(String(result.selected?.model ?? ''), ASTRA_MODEL_PATTERN, JSON.stringify(request));
    }
    assert.ok(allSelectedModels.includes('gpt-6.2-sol'));
    assert.ok(allSelectedModels.includes('gpt-5.6-luna'));
    for (const approvedPair of policy.approvedPairs) {
        assert.doesNotMatch(policy.modelByName[approvedPair.model].id, ASTRA_MODEL_PATTERN);
    }
});

test('poteto plugin aliases use worker routing without advisor privileges', () => {
    for (const agent_type of ['poteto-agent', 'pstack:poteto-agent']) {
        const result = route({ agent_type, model: 'Sol', reasoning_effort: 'low' });
        assert.deepEqual(result.selected, { model: 'gpt-5.6-luna', effort: 'xhigh' });
    }
});

test('every approved pair returns its literal native pair', () => {
    const expected = [
        [['Luna', 'high'], ['gpt-5.6-luna', 'high']],
        [['Luna', 'xhigh'], ['gpt-5.6-luna', 'xhigh']],
        [['Luna', 'max'], ['gpt-5.6-luna', 'max']],
        [['Sol', 'high'], ['gpt-6.2-sol', 'high']],
        [['Sol', 'xhigh'], ['gpt-6.2-sol', 'xhigh']],
    ];
    for (const [[model, effort], [expectedModel, expectedEffort]] of expected) {
        const result = route({ model, reasoning_effort: effort });
        assert.ok(['pass', 'remapped'].includes(result.status));
        assert.deepEqual(result.selected, { model: expectedModel, effort: expectedEffort });
        const nativeRoute = route({ model: expectedModel, reasoning_effort: expectedEffort });
        assert.equal(nativeRoute.status, 'pass');
        assert.deepEqual(nativeRoute.selected, { model: expectedModel, effort: expectedEffort });
    }
    const advisor = advisorRoute({
        model: 'Sol',
        reasoning_effort: 'high',
        agent_type: 'team-advisor',
    });
    assert.equal(advisor.status, 'remapped');
    assert.deepEqual(advisor.selected, { model: 'gpt-6.2-sol', effort: 'high' });
});

test('selector exclusions keep Sol Medium out while direct routing remaps', () => {
    const policy = loadSubagentModelPolicy();
    assert.equal(policy.selectorExclusions.has('sol/medium'), true);
    const result = route({ model: 'Sol', reasoning_effort: 'medium' });
    assert.equal(result.status, 'remapped');
    assert.deepEqual(result.selected, { model: 'gpt-5.6-luna', effort: 'max' });

    const rawPolicy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    rawPolicy.selectorExclusions = [{ model: 'missing', effort: 'medium' }];
    assert.throws(
        () => validateSubagentModelPolicy(rawPolicy),
        /selectorExclusions entry has unknown model/,
    );
});

test('every automatic replacement returns its literal destination', () => {
    for (const [[model, effort], [expectedModel, expectedEffort]] of replacements) {
        const result = route({ model, reasoning_effort: effort });
        assert.equal(result.status, 'remapped');
        assert.deepEqual(result.selected, { model: expectedModel, effort: expectedEffort });
    }
});

test('advisor and worker Sol Low and Medium use role-specific replacements', () => {
    for (const effort of ['low', 'medium']) {
        assert.deepEqual(
            advisorRoute({ model: 'Sol', reasoning_effort: effort, agent_type: 'team-advisor' }).selected,
            { model: 'gpt-6.2-sol', effort: 'xhigh' },
        );
    }
    assert.deepEqual(
        route({ model: 'Sol', reasoning_effort: 'low', agent_type: 'worker' }).selected,
        { model: 'gpt-5.6-luna', effort: 'xhigh' },
    );
    assert.deepEqual(
        route({ model: 'Sol', reasoning_effort: 'medium', agent_type: 'worker' }).selected,
        { model: 'gpt-5.6-luna', effort: 'max' },
    );
    assert.deepEqual(
        advisorRoute({ model: 'Sol', reasoning_effort: 'max', agent_type: 'team-advisor' }).selected,
        { model: 'gpt-6.2-sol', effort: 'xhigh' },
    );
});

test('registered advisor roles satisfy advisory authorization', () => {
    const result = advisorRoute({
        model: 'Sol',
        reasoning_effort: 'high',
        agent_type: 'team-advisor',
    });

    assert.deepEqual(result.selected, { model: 'gpt-6.2-sol', effort: 'high' });
});

test('a policy from the first stack revision remains routable', () => {
    const legacyPolicy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    delete legacyPolicy.roles.trustedAdvisor;
    const result = advisorRoute(
        {
            model: 'Sol',
            reasoning_effort: 'high',
            agent_type: 'team-advisor',
        },
        { policy: legacyPolicy },
    );
    assert.deepEqual(result.selected, { model: 'gpt-6.2-sol', effort: 'high' });
});

test('an advisor role claim cannot grant advisory authorization', () => {
    const result = route({
        model: 'Sol',
        reasoning_effort: 'high',
        agent_type: 'team-advisor',
    });
    assert.equal(result.status, 'blocked');
    assert.equal(result.diagnostic, 'advisor role is not trusted');
});

test('Sol Light resolves as Sol Low', () => {
    const result = route({ model: 'Sol', reasoning_effort: 'Light' });
    assert.deepEqual(result.requested, { model: 'gpt-6.2-sol', effort: 'low' });
    assert.deepEqual(result.selected, { model: 'gpt-5.6-luna', effort: 'xhigh' });
});

test('missing advisor settings use the policy default', () => {
    const result = advisorRoute({ agent_type: 'team-advisor' });
    assert.deepEqual(result.selected, { model: 'gpt-6.2-sol', effort: 'xhigh' });
});

test('the advisor bridge blocks malformed input', () => {
    const bridgePath = join(PACKAGE_ROOT, 'scripts', 'resolve_advisor_model_route.mjs');
    assert.throws(
        () => execFileSync(process.execPath, [bridgePath], { encoding: 'utf8', input: '{' }),
        error => {
            assert.equal(error.status, 1);
            assert.deepEqual(JSON.parse(error.stdout), {
                status: 'blocked',
                diagnostic: 'advisor route input is not valid JSON',
            });
            return true;
        },
    );
});

test('the advisor bridge routes Sol Medium to Sol Xhigh', () => {
    const bridgePath = join(PACKAGE_ROOT, 'scripts', 'resolve_advisor_model_route.mjs');
    const bridgeExecution = spawnSync(
        process.execPath,
        [bridgePath],
        {
            encoding: 'utf8',
            input: JSON.stringify({ model: 'Sol', reasoning_effort: 'medium' }),
        },
    );
    assert.equal(bridgeExecution.status, 0);
    assert.equal(bridgeExecution.stderr, '');
    const advisorDecision = JSON.parse(bridgeExecution.stdout);
    assert.equal(advisorDecision.status, 'remapped');
    assert.equal(advisorDecision.role, 'advisor');
    assert.equal(advisorDecision.diagnostic, null);
    assert.deepEqual(advisorDecision.selected, { model: 'gpt-6.2-sol', effort: 'xhigh' });
});

test('missing worker settings preserve parent inheritance', () => {
    const input = { message: 'keep', agent_type: 'worker' };
    const result = routeSubagentToolInput(input);
    assert.equal(result.status, 'inherited');
    assert.strictEqual(result.updatedInput, input);
});

test('Sol without an effort stays blocked while it has two approved efforts', () => {
    const result = route(
        { model: 'Sol' },
        { allowMissingEffort: true },
    );
    assert.equal(result.status, 'blocked');
    assert.equal(result.diagnostic, 'effort is required for this model');
});

test('unknown input holds with a short diagnostic', () => {
    assert.match(route({ model: 'Unknown', reasoning_effort: 'medium' }).diagnostic, /model is unknown/);
    assert.match(route({ model: 'Terra', reasoning_effort: 'future' }).diagnostic, /effort is unknown/);
    assert.match(route({ model: 'Sol', reasoning_effort: 'medium', agent_type: 'unregistered' }).diagnostic, /role is unknown/);
});

test('dual effort fields hold instead of leaving one stale', () => {
    const result = route({ model: 'Luna', reasoning_effort: 'low', effort: 'low' });
    assert.equal(result.status, 'blocked');
    assert.match(result.diagnostic, /effort fields are ambiguous/);
});

test('native values with case or whitespace differences are canonicalized', () => {
    const result = routeSubagentToolInput({
        model: ' gpt-6.2-sol ',
        reasoning_effort: 'Medium',
        message: 'keep',
    });
    assert.equal(result.status, 'remapped');
    assert.deepEqual(result.updatedInput, {
        model: 'gpt-5.6-luna',
        reasoning_effort: 'max',
        message: 'keep',
    });
});

test('unavailable replacements hold the spawn', () => {
    const result = route(
        { model: 'Sol', reasoning_effort: 'medium' },
        { availableModelIds: ['gpt-6.2-sol'] },
    );
    assert.equal(result.status, 'blocked');
    assert.match(result.diagnostic, /replacement model is unavailable/);
});

test('the tool route copies every non-routing field', () => {
    const input = {
        assignment: 'preserve',
        message: 'do the work',
        child_permissions: { shell: 'ask' },
        output_contract: ['summary'],
        model: 'Terra',
        reasoning_effort: 'Medium',
    };
    const result = routeSubagentToolInput(input);
    assert.deepEqual(result.updatedInput, {
        assignment: 'preserve',
        message: 'do the work',
        child_permissions: { shell: 'ask' },
        output_contract: ['summary'],
        model: 'gpt-5.6-luna',
        reasoning_effort: 'xhigh',
    });
    assert.deepEqual(input, {
        assignment: 'preserve',
        message: 'do the work',
        child_permissions: { shell: 'ask' },
        output_contract: ['summary'],
        model: 'Terra',
        reasoning_effort: 'Medium',
    });
});

test('a second route pass is idempotent', () => {
    const first = routeSubagentToolInput(
        { model: 'Sol', reasoning_effort: 'medium', message: 'keep' },
        {},
    );
    const second = routeSubagentToolInput(first.updatedInput);
    assert.equal(first.status, 'remapped');
    assert.equal(second.status, 'pass');
    assert.deepEqual(second.updatedInput, first.updatedInput);
});

test('a temporary policy copy changes the next route without source edits', () => {
    const temporaryRoot = mkdtempSync(join(tmpdir(), 'subagent-policy-'));
    try {
        const temporaryPolicy = join(temporaryRoot, 'policy.json');
        const sourceText = readFileSync(POLICY_SOURCE, 'utf8');
        const policy = JSON.parse(sourceText);
        writeFileSync(temporaryPolicy, sourceText);
        assert.deepEqual(route(
            { model: 'Sol', reasoning_effort: 'medium' },
            { policyPath: temporaryPolicy },
        ).selected, { model: 'gpt-5.6-luna', effort: 'max' });
        policy.roleReplacements = policy.roleReplacements.map(replacement => (
            replacement.role === 'worker'
                && replacement.requested.model === 'sol'
                && replacement.requested.effort === 'medium'
                ? { ...replacement, selected: { model: 'luna', effort: 'xhigh' } }
                : replacement
        ));
        writeFileSync(temporaryPolicy, JSON.stringify(policy));
        const updatedRoute = route(
            { model: 'Sol', reasoning_effort: 'medium' },
            { policyPath: temporaryPolicy },
        );
        assert.deepEqual(updatedRoute.selected, { model: 'gpt-5.6-luna', effort: 'xhigh' });
        assert.equal(readFileSync(POLICY_SOURCE, 'utf8'), sourceText);
    } finally {
        rmSync(temporaryRoot, { recursive: true, force: true });
    }
});

test('malformed policy data fails validation', () => {
    assert.throws(
        () => validateSubagentModelPolicy({ schemaVersion: 1 }),
        error => error instanceof SubagentModelPolicyError && /models must be an object/.test(error.message),
    );
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    assert.throws(
        () => validateSubagentModelPolicy({
            ...policy,
            replacements: [
                {
                    requested: { model: 'terra', effort: 'medium' },
                    selected: { model: 'terra', effort: 'medium' },
                },
            ],
        }),
        /replacement target is not approved/,
    );
    const blocked = resolveSubagentModelRoute(
        { model: 'Terra', reasoning_effort: 'medium' },
        { policy: { schemaVersion: 1 } },
    );
    assert.equal(blocked.status, 'blocked');
    assert.match(blocked.diagnostic, /models must be an object/);
});

test('a copied policy cannot forge the validated-policy marker', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    const validatedPolicy = validateSubagentModelPolicy(policy);
    const copiedPolicy = { ...validatedPolicy, models: {} };
    const result = resolveSubagentModelRoute(
        { model: 'Terra', reasoning_effort: 'medium' },
        { policy: copiedPolicy },
    );
    assert.equal(result.status, 'blocked');
    assert.match(result.diagnostic, /models must not be empty/);
});

test('normalized effort aliases resolve from the validated policy', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    policy.efforts.aliases = { Light: 'LOW' };
    const validatedPolicy = validateSubagentModelPolicy(policy);
    const result = resolveSubagentModelRoute(
        { model: 'Sol', reasoning_effort: 'Light' },
        { policy: validatedPolicy },
    );
    assert.deepEqual(result.requested, { model: 'gpt-6.2-sol', effort: 'low' });
    assert.deepEqual(result.selected, { model: 'gpt-5.6-luna', effort: 'xhigh' });
});

test('inheritance aliases cannot shadow model aliases', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    policy.inheritanceAliases = ['astra'];
    assert.throws(
        () => validateSubagentModelPolicy(policy),
        /inheritance alias conflicts with a model alias/,
    );
});

test('model names cannot collide after normalization', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    policy.models.Astra = { id: 'gpt-6-astra-copy', aliases: [] };
    assert.throws(
        () => validateSubagentModelPolicy(policy),
        /model name is ambiguous: astra/,
    );
});

test('combined role routes must end at an approved terminal pair', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    const terraMediumReplacement = policy.replacements.find(replacement => (
        replacement.requested.model === 'terra'
        && replacement.requested.effort === 'medium'
    ));
    terraMediumReplacement.selected = { model: 'sol', effort: 'high' };
    policy.roleReplacements.push({
        role: 'worker',
        requested: { model: 'sol', effort: 'high' },
        selected: { model: 'luna', effort: 'high' },
    });
    assert.throws(
        () => validateSubagentModelPolicy(policy),
        /replacement destination is not terminal/,
    );
});

test('replacement cycles fail policy validation', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    policy.replacements.push(
        {
            requested: { model: 'luna', effort: 'high' },
            selected: { model: 'luna', effort: 'xhigh' },
        },
        {
            requested: { model: 'luna', effort: 'xhigh' },
            selected: { model: 'luna', effort: 'high' },
        },
    );
    assert.throws(
        () => validateSubagentModelPolicy(policy),
        /replacement cycle includes/,
    );
});

test('base replacement targets must be approved for every role', () => {
    const policy = JSON.parse(readFileSync(POLICY_SOURCE, 'utf8'));
    policy.replacements = policy.replacements.map(replacement => (
        replacement.requested.model === 'terra' && replacement.requested.effort === 'medium'
            ? { ...replacement, selected: { model: 'astra', effort: 'high' } }
            : replacement
    ));
    assert.throws(
        () => validateSubagentModelPolicy(policy),
        /replacement target is not approved: astra\/high/,
    );
});

test('policy aliases stay in the policy file', () => {
    const source = readFileSync(join(PACKAGE_ROOT, 'scripts', 'subagent_model_policy.mjs'), 'utf8');
    assert.doesNotMatch(source, /gpt-5\.6-(?:luna|sol|terra)|gpt-6\.2-sol|gpt-6-astra/);
});
