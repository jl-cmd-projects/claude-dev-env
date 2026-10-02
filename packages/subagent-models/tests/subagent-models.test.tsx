import { test, expect } from 'claude-code/testing'
import type { AgentSpawnInput, ConfigSetInput, On, TurnStepInput } from 'claude-code'

type World = {
  running: string[]
  toasts: string[]
  spawnedModels: (string | undefined)[]
  steps: TurnStepInput[]
  statuses: (string | undefined)[]
  configWrites: { key: string; value: unknown }[]
}

function engine(on: On): World {
  const world: World = { running: [], toasts: [], spawnedModels: [], steps: [], statuses: [], configWrites: [] }
  on('agent.spawn', (_$, e) => {
    world.spawnedModels.push(e.model)
    return { model: e.model ?? e.parentModel, agentId: 'agent-1' }
  })
  on('turn.step', async function* (_$, e) {
    world.steps.push(e)
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as never, usage: null }
  })
  on('agent.offer', () => ({ isOffered: true }))
  on('agent.list', () => ({ value: world.running.map(id => ({ id, description: id, type: 'general-purpose', status: 'running' })) }) as never)
  on('ui.toast', (_$, e) => (world.toasts.push(typeof e === 'string' ? e : (e as { text: string }).text), { value: undefined }) as never)
  on('ui.status', (_$, e) => (world.statuses.push((e as { text?: string }).text), { value: undefined }) as never)
  on('config.set', (_$, e: ConfigSetInput) => (world.configWrites.push({ key: e.key, value: e.value }), { value: e.value }))
  return world
}

const spawnOf = (model: string | undefined, fork = false): AgentSpawnInput => ({
  tool_use_id: 'toolu_1',
  prompt: 'Read README.md.',
  description: 'read readme',
  subagentType: 'general-purpose',
  provider: { plugin: 'engine', tier: 'core' } as never,
  model,
  parentModel: 'claude-opus-5-5',
  background: true,
  fork,
})

const spawnAs = (subagentType: string): AgentSpawnInput => ({ ...spawnOf('opus'), subagentType })

async function offer($: { agent: { offer: (e: never) => Promise<{ isOffered: boolean }> } }, agent: string) {
  return $.agent.offer({ agent, description: '', source: 'built-in', provider: { plugin: 'engine', tier: 'core' } } as never)
}

const stepOf = (model: string, agentId?: string, effort?: TurnStepInput['effort']): TurnStepInput => ({
  turnId: 't1',
  index: 0,
  model,
  effort,
  messageCount: 1,
  agentId,
})

async function runStep($: { turn: { step: (e: TurnStepInput) => AsyncGenerator<unknown, unknown> & { result: Promise<unknown> } } }, e: TurnStepInput) {
  const stream = $.turn.step(e)
  for await (const _chunk of stream) {
  }
  return stream.result
}

async function command($: { command: { run: (e: never) => Promise<{ text?: string }> } }, args: string) {
  return $.command.run({ command: 'subagent-models', args, origin: { kind: 'composer' }, presentation: {} } as never)
}

test('moves a fable spawn to opus', async ($, on) => {
  const world = engine(on)
  const result = await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['opus'])
  expect(result.deny).toBeUndefined()
})

test('moves a sonnet spawn to opus', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('sonnet'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('reads a full fable id as fable', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf(' Claude-Fable-5-1 '))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('passes an opus spawn as given', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('opus'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('passes a haiku spawn while haiku is on', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('haiku'))
  expect(world.spawnedModels).toEqual(['haiku'])
})

test('passes a spawn with no model', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf(undefined))
  expect(world.spawnedModels).toEqual([undefined])
})

test('passes a fork whatever model it names', async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('fable', true))
  expect(world.spawnedModels).toEqual(['fable'])
})

test('passes a fable spawn while fable is on', { options: { fable: 'on' } }, async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['fable'])
})

test('moves to the default model the settings name', { options: { defaultModel: 'haiku' } }, async ($, on) => {
  const world = engine(on)
  await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['haiku'])
})

test('refuses a turned-off spawn when offAction is deny', { options: { offAction: 'deny' } }, async ($, on) => {
  const world = engine(on)
  const result = await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual([])
  expect(result.deny).toBe('Subagent model fable is turned off. Spawn subagents on opus and ask for medium effort in the brief.')
})

test('sets medium effort on a subagent step', async ($, on) => {
  const world = engine(on)
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'high'))
  expect(world.steps[0]?.effort).toBe('medium')
  expect(world.steps[0]?.model).toBe('claude-opus-5-5')
})

test('leaves a main-session step untouched', async ($, on) => {
  const world = engine(on)
  await runStep($ as never, stepOf('claude-fable-5-1', undefined, 'high'))
  expect(world.steps[0]?.effort).toBe('high')
  expect(world.steps[0]?.model).toBe('claude-fable-5-1')
})

test('keeps the step effort when effort is inherit', { options: { effort: 'inherit' } }, async ($, on) => {
  const world = engine(on)
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'high'))
  expect(world.steps[0]?.effort).toBe('high')
})

test('moves a subagent step on a turned-off model to the default model', async ($, on) => {
  const world = engine(on)
  await runStep($ as never, stepOf('claude-fable-5-1', 'agent-1'))
  expect(world.steps[0]?.model).toBe('opus')
})

test('a session override turns fable on for this session only', async ($, on) => {
  const world = engine(on)
  const answer = await command($ as never, 'fable on')
  expect(answer.text).toMatch(/fable on/)
  await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['fable'])
  expect(world.configWrites).toEqual([])
})

test('a session override sets the effort of later subagent steps', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'effort high')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  expect(world.steps[0]?.effort).toBe('high')
})

test('refuses a value outside the field options', async ($, on) => {
  const world = engine(on)
  const answer = await command($ as never, 'fable maybe')
  expect(answer.text).toMatch(/fable takes on, off/)
  await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('reset drops the session overrides', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'fable on')
  await command($ as never, 'reset')
  await $.agent.spawn(spawnOf('fable'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('save writes the session values to the defaults', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'fable on')
  await command($ as never, 'save')
  expect(world.configWrites).toContainEqual({ key: 'subagent-models.fable', value: 'on' })
})

test('no arguments prints the values in force', async ($, on) => {
  engine(on)
  await command($ as never, 'sonnet on')
  const answer = await command($ as never, '')
  expect(answer.text).toMatch(/sonnet on \(this session\)/)
  expect(answer.text).toMatch(/fable off/)
  expect(answer.text).toMatch(/effort medium/)
})

test('the status line shows the default model and effort', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'effort low')
  expect(world.statuses.at(-1)).toBe('subagents: opus/low (session)')
})

test('turning an agent type off hides it from the model', async ($, on) => {
  engine(on)
  await command($ as never, 'agent Explore off')
  expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
  expect((await offer($ as never, 'Plan')).isOffered).toBe(true)
})

test('turning an agent type off refuses its spawn', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'agent Explore off')
  const result = await $.agent.spawn(spawnAs('Explore'))
  expect(result.deny).toBe('Subagent type Explore is turned off. Pick another subagent_type.')
  expect(world.spawnedModels).toEqual([])
})

test('an agent type turned back on spawns again', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'agent Explore off')
  await command($ as never, 'agent Explore on')
  await $.agent.spawn(spawnAs('Explore'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('the disabledAgents default turns agent types off', { options: { disabledAgents: 'Explore, Plan' } }, async ($, on) => {
  const world = engine(on)
  expect((await $.agent.spawn(spawnAs('Plan'))).deny).toMatch(/Plan is turned off/)
  expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
  await $.agent.spawn(spawnAs('general-purpose'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('agents lists every offered type with its switch', async ($, on) => {
  engine(on)
  await offer($ as never, 'Plan')
  await offer($ as never, 'Explore')
  await command($ as never, 'agent Explore off')
  const answer = await command($ as never, 'agents')
  expect(answer.text).toBe('Explore off (this session)\nPlan on')
})

test('save writes the turned-off agent types to the defaults', { options: { disabledAgents: 'Plan' } }, async ($, on) => {
  const world = engine(on)
  await command($ as never, 'agent Explore off')
  await command($ as never, 'save')
  expect(world.configWrites).toContainEqual({ key: 'subagent-models.disabledAgents', value: 'Explore, Plan' })
})

test('the listing names the turned-off agent types', { options: { disabledAgents: 'Plan' } }, async ($, on) => {
  engine(on)
  const answer = await command($ as never, '')
  expect(answer.text).toMatch(/agents off: Plan$/)
})

test('turning opus off moves an opus spawn to the default model', { options: { defaultModel: 'haiku' } }, async ($, on) => {
  const world = engine(on)
  await command($ as never, 'opus off')
  await $.agent.spawn(spawnOf('opus'))
  expect(world.spawnedModels).toEqual(['haiku'])
})

test('refuses turning off the default model', async ($, on) => {
  const world = engine(on)
  const answer = await command($ as never, 'opus off')
  expect(answer.text).toBe('opus is the default model. Pick another defaultModel before turning opus off.')
  await $.agent.spawn(spawnOf('opus'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('refuses a default model that is turned off', async ($, on) => {
  engine(on)
  const answer = await command($ as never, 'defaultModel fable')
  expect(answer.text).toBe('fable is turned off. Turn fable on before making it the default model.')
})

test('a malformed agent command prints the usage', async ($, on) => {
  engine(on)
  expect((await command($ as never, 'agent Explore maybe')).text).toMatch(/^Usage:/)
  expect((await command($ as never, 'agent')).text).toMatch(/^Usage:/)
})

test('with applyToRunning on, a running subagent moves to a new effort', async ($, on) => {
  const world = engine(on)
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await command($ as never, 'effort high')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  expect(world.steps.map(step => step.effort)).toEqual(['medium', 'high'])
})

test('with applyToRunning off, a running subagent keeps the effort it started with', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'applyToRunning off')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await command($ as never, 'effort high')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-2', 'low'))
  expect(world.steps.map(step => step.effort)).toEqual(['medium', 'medium', 'high'])
})

test('apply moves every running subagent to the current effort', async ($, on) => {
  const world = engine(on)
  world.running = ['agent-1']
  await command($ as never, 'applyToRunning off')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await command($ as never, 'effort max')
  const answer = await command($ as never, 'apply')
  expect(answer.text).toBe('effort max applied to 1 running subagent.')
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  expect(world.steps.map(step => step.effort)).toEqual(['medium', 'max'])
})

const BAR_TARGET = {
  plugin: 'subagent-models',
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120 } as never,
} as const

test('the bar sets effort, models and agent types on every surface', async ($, on) => {
  const world = engine(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    await command($ as never, 'reset')
    world.spawnedModels = []
    await offer($ as never, 'Explore')
    const ui = await $.ui.mount({ ...BAR_TARGET, surface })
    expect((await ui.find({ key: 'effort' }))?.props.value).toBe('medium')
    await ui.select({ key: 'effort', value: 'high' })
    expect((await ui.find({ key: 'effort' }))?.props.value).toBe('high')
    await ui.press({ key: 'model-fable' })
    await $.agent.spawn(spawnOf('fable'))
    expect(world.spawnedModels).toEqual(['fable'])
    await ui.select({ key: 'agents', value: 'Explore' })
    expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
    expect(world.toasts).toContain('agent Explore off for this session.')
    await ui.select({ key: 'agents', value: 'Explore' })
    expect((await offer($ as never, 'Explore')).isOffered).toBe(true)
    await ui.unmount()
  }
})

test('the bar refuses turning off the default model', async ($, on) => {
  const world = engine(on)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'terminal' })
  await ui.press({ key: 'model-opus' })
  expect(world.toasts).toContain('opus is the default model. Pick another defaultModel before turning opus off.')
  await $.agent.spawn(spawnOf('opus'))
  expect(world.spawnedModels).toEqual(['opus'])
})

test('the bar applies effort to running subagents and shows their count', async ($, on) => {
  const world = engine(on)
  world.running = ['agent-1', 'agent-2']
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  expect((await ui.find({ key: 'applyToRunning' }))?.props.label).toBe('running 2')
  await ui.select({ key: 'applyToRunning', value: 'off' })
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await ui.select({ key: 'effort', value: 'xhigh' })
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  await ui.press({ key: 'apply' })
  await runStep($ as never, stepOf('claude-opus-5-5', 'agent-1', 'low'))
  expect(world.steps.map(step => step.effort)).toEqual(['medium', 'medium', 'xhigh'])
  expect(world.toasts).toContain('effort xhigh applied to 2 running subagents.')
})

test('minimize collapses the bar to a pill that expands it, and the bar command toggles', async ($, on) => {
  engine(on)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'terminal' })
  await ui.press({ key: 'minimize' })
  expect(await ui.find({ key: 'effort' })).toBeUndefined()
  expect(await ui.find({ key: 'expand' })).toBeDefined()
  await ui.press({ key: 'expand' })
  expect(await ui.find({ key: 'effort' })).toBeDefined()
  expect((await command($ as never, 'bar')).text).toBe('Subagent bar minimized.')
  expect(await ui.find({ key: 'expand' })).toBeDefined()
  expect((await command($ as never, 'bar')).text).toBe('Subagent bar expanded.')
})

test('the more menu saves the session values as defaults', async ($, on) => {
  const world = engine(on)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.select({ key: 'effort', value: 'max' })
  await ui.select({ key: 'more', value: 'save' })
  expect(world.configWrites).toContainEqual({ key: 'subagent-models.effort', value: 'max' })
})
