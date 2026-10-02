import { test, expect } from 'claude-code/testing'
import type { AgentSpawnInput, ConfigSetInput, On, TurnStepInput } from 'claude-code'

type World = {
  running: string[]
  toasts: string[]
  spawnedModels: (string | undefined)[]
  steps: TurnStepInput[]
  statuses: (string | undefined)[]
  configWrites: { key: string; value: unknown }[]
  store: Record<string, unknown>
  files: Record<string, string>
}

const LISTED_SKILLS = [
  { name: 'simplify', source: 'built-in', tokens: 10 },
  { name: 'tdd', source: 'plugin', pluginName: 'pstack', tokens: 10 },
  { name: 'pstack:why', source: 'plugin', pluginName: 'pstack', tokens: 10 },
]

function engine(on: On): World {
  const world: World = { running: [], toasts: [], spawnedModels: [], steps: [], statuses: [], configWrites: [], store: {}, files: {} }
  on('agent.spawn', (_$, e) => {
    world.spawnedModels.push(e.model)
    return { model: e.model ?? e.parentModel, agentId: 'agent-1' }
  })
  on('turn.step', async function* (_$, e) {
    world.steps.push(e)
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as never, usage: null }
  })
  on('agent.offer', () => ({ isOffered: true }))
  on('skill.prompt', (_$, e) => ({ text: e.text }))
  on('session.usage', () => ({ value: { context: { breakdown: { skills: { skillFrontmatter: LISTED_SKILLS } } } } }) as never)
  on('agent.list', () => ({ value: world.running.map(id => ({ id, description: id, type: 'general-purpose', status: 'running' })) }) as never)
  on('ui.toast', (_$, e) => (world.toasts.push(typeof e === 'string' ? e : (e as { text: string }).text), { value: undefined }) as never)
  on('ui.status', (_$, e) => (world.statuses.push((e as { text?: string }).text), { value: undefined }) as never)
  on('config.set', (_$, e: ConfigSetInput) => (world.configWrites.push({ key: e.key, value: e.value }), { value: e.value }))
  on('store.get', (_$, e) => ({ value: world.store[e.key] }) as never)
  on('store.set', (_$, e) => ((world.store[e.key] = e.value), { value: undefined }) as never)
  on('fs.read', (_$, e) => {
    const text = Object.entries(world.files).find(([name]) => e.path.endsWith(name))?.[1]
    if (text === undefined) throw new Error(`missing ${e.path}`)
    return { value: text } as never
  })
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

test('no command leaves text on the status line', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'effort low')
  await command($ as never, 'agent Explore off')
  await command($ as never, 'reset')
  expect(world.statuses.filter(text => text !== undefined)).toEqual([])
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
  const lines = (await command($ as never, 'off')).text?.split('\n') ?? []
  expect(lines[0]).toBe('Usage: /subagent-models <command>')
  expect(lines.filter(line => line.startsWith('- ')).map(line => line.split(':')[0])).toEqual([
    '- <field> <value>',
    '- agents',
    '- agent <type> on|off',
    '- skills',
    '- skill <name> on|off',
    '- seed <file>',
    '- bar',
    '- apply',
    '- save',
    '- reset',
  ])
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
    expect(await ui.find({ key: 'agent-Explore' })).toBeUndefined()
    await ui.press({ key: 'agents' })
    await ui.press({ key: 'agent-Explore' })
    expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
    expect(world.toasts).toContain('agent Explore off for this session.')
    await ui.press({ key: 'agent-Explore' })
    expect((await offer($ as never, 'Explore')).isOffered).toBe(true)
    await ui.press({ key: 'agents' })
    expect(await ui.find({ key: 'agent-Explore' })).toBeUndefined()
    await ui.unmount()
  }
})

test('the agents panel stays open across picks and enables or disables every type', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  await offer($ as never, 'Explore')
  await offer($ as never, 'Plan')
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.press({ key: 'agents' })
  await ui.press({ key: 'agents-disable-all' })
  expect(world.toasts).toContain('2 agent types off for this session.')
  expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
  expect((await offer($ as never, 'Plan')).isOffered).toBe(false)
  expect(await ui.find({ key: 'agent-Plan' })).toBeDefined()
  await ui.press({ key: 'agent-Plan' })
  expect((await offer($ as never, 'Plan')).isOffered).toBe(true)
  expect((await offer($ as never, 'Explore')).isOffered).toBe(false)
  await ui.press({ key: 'agents-enable-all' })
  expect((await offer($ as never, 'Explore')).isOffered).toBe(true)
  await ui.press({ key: 'agents' })
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

const MODE_TARGET = {
  plugin: 'subagent-models',
  component: 'SessionMode',
  props: { modes: ['focus'] } as never,
} as const

test('the footer pill opens the bar, the minimize button closes it, and the bar command toggles', async ($, on) => {
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine band</Text>
  })
  engine(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    await command($ as never, 'reset')
    const bar = await $.ui.mount({ ...BAR_TARGET, surface })
    const footer = await $.ui.mount({ ...MODE_TARGET, surface })
    expect(await footer.find({ type: 'Text', text: 'focus' })).toBeDefined()
    await bar.press({ key: 'minimize' })
    expect(await bar.find({ key: 'effort' })).toBeUndefined()
    expect(await bar.find({ type: 'Text', text: 'engine band' })).toBeDefined()
    await footer.press({ key: 'pill' })
    expect(await bar.find({ key: 'effort' })).toBeDefined()
    expect((await command($ as never, 'bar')).text).toBe('Subagent bar minimized.')
    expect((await command($ as never, 'bar')).text).toBe('Subagent bar expanded.')
    await bar.unmount()
    await footer.unmount()
  }
})

test('the more menu saves the session values as defaults', async ($, on) => {
  const world = engine(on)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.select({ key: 'effort', value: 'max' })
  await ui.select({ key: 'more', value: 'save' })
  expect(world.configWrites).toContainEqual({ key: 'subagent-models.effort', value: 'max' })
})

async function skillText($: { skill: { prompt: (e: never) => Promise<{ text: string }> } }, skill: string) {
  return (await $.skill.prompt({ skill, text: 'skill body' } as never)).text
}

test('the skills panel loads the session skills and its chips turn a skill off and on', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  expect(await ui.find({ key: 'skill-pstack:tdd' })).toBeUndefined()
  await ui.press({ key: 'skills' })
  expect(await ui.find({ key: 'skill-simplify' })).toBeDefined()
  expect(await ui.find({ key: 'skill-pstack:tdd' })).toBeDefined()
  expect(await skillText($ as never, 'pstack:tdd')).toBe('skill body')
  await ui.press({ key: 'skill-pstack:tdd' })
  expect(world.toasts).toContain('skill pstack:tdd off for this session.')
  expect(await skillText($ as never, 'pstack:tdd')).toMatch(/turned off/)
  expect(await skillText($ as never, 'simplify')).toBe('skill body')
  await ui.press({ key: 'skill-pstack:tdd' })
  expect(await skillText($ as never, 'pstack:tdd')).toBe('skill body')
  await ui.press({ key: 'skills-disable-all' })
  expect(world.toasts).toContain('3 skills off for this session.')
  expect(await skillText($ as never, 'simplify')).toMatch(/turned off/)
  await ui.press({ key: 'skills-enable-all' })
  expect(await skillText($ as never, 'simplify')).toBe('skill body')
  await ui.press({ key: 'skills' })
  expect(await ui.find({ key: 'skill-simplify' })).toBeUndefined()
})

test('a skill command matches a namespaced skill by its short name and lists the skills', async ($, on) => {
  engine(on)
  await command($ as never, 'reset')
  await command($ as never, 'skill tdd off')
  expect(await skillText($ as never, 'pstack:tdd')).toMatch(/turned off/)
  expect(await skillText($ as never, 'pstack:why')).toBe('skill body')
  const listing = await command($ as never, 'skills')
  expect(listing.text).toMatch(/pstack:tdd on/)
  expect(listing.text).toMatch(/tdd off \(this session\)/)
})

test('save writes the turned-off skills to the defaults', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  await command($ as never, 'skill simplify off')
  await command($ as never, 'save')
  expect(world.configWrites).toContainEqual({ key: 'subagent-models.disabledSkills', value: 'simplify' })
})

async function offerMany($: unknown, count: number) {
  for (let index = 0; index < count; index += 1) await offer($ as never, `team:agent-${String(index).padStart(2, '0')}`)
}

function paneEngine(on: On) {
  const panes = { opened: [] as string[], closed: [] as string[] }
  on('ui.open', (_$, e) => (panes.opened.push(e.id), { value: { isPlaced: true } }) as never)
  on('ui.close', (_$, e) => (panes.closed.push(e.id), { value: undefined }) as never)
  return panes
}

const PANE_TARGET = {
  plugin: 'subagent-models',
  component: 'Pane',
  requestId: 'subagent-agents',
  props: { title: 'Agent types', isFocused: false, bodyColumns: 100, placement: 'dock' } as never,
} as const

test('a list of 16 stays in the bar and opens no pane', async ($, on) => {
  engine(on)
  const panes = paneEngine(on)
  await command($ as never, 'reset')
  await offerMany($, 16)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.press({ key: 'agents' })
  expect(await ui.find({ key: 'agent-team:agent-15' })).toBeDefined()
  expect(panes.opened).toEqual([])
  await ui.press({ key: 'agents' })
})

test('a list of 17 opens a side pane, and the pane chips drive the same switches', async ($, on) => {
  const world = engine(on)
  const panes = paneEngine(on)
  await command($ as never, 'reset')
  await offerMany($, 17)
  const bar = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await bar.press({ key: 'agents' })
  expect(panes.opened).toEqual(['subagent-agents'])
  expect(await bar.find({ key: 'agent-team:agent-16' })).toBeUndefined()
  const pane = await $.ui.mount({ ...PANE_TARGET, surface: 'desktop' })
  expect(await pane.find({ key: 'agent-team:agent-16' })).toBeDefined()
  await pane.press({ key: 'agent-team:agent-16' })
  expect(world.toasts).toContain('agent team:agent-16 off for this session.')
  expect((await offer($ as never, 'team:agent-16')).isOffered).toBe(false)
  await pane.press({ key: 'agents-disable-all' })
  expect(world.toasts).toContain('17 agent types off for this session.')
  await bar.press({ key: 'agents' })
  expect(panes.closed).toEqual(['subagent-agents'])
  await pane.unmount()
  await bar.unmount()
})

type DrawnNode = { type?: string; props?: { key?: string; width?: number; children?: unknown }; children?: DrawnNode[] }

function cellsHolding(node: DrawnNode, keyPrefix: string): DrawnNode[] {
  const own = node.type === 'Box' && (node.children ?? []).some(child => child.props?.key?.startsWith(keyPrefix)) ? [node] : []
  return [...own, ...(node.children ?? []).flatMap(child => cellsHolding(child, keyPrefix))]
}

test('every panel chip sits in a cell of one width, wide enough for the longest name', async ($, on) => {
  engine(on)
  await command($ as never, 'reset')
  await offer($ as never, 'Explore')
  await offer($ as never, 'brand-voice:conversation-analysis-extra')
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.press({ key: 'agents' })
  const cells = cellsHolding((await ui.drawn()) as DrawnNode, 'agent-')
  const widths = new Set(cells.map(cell => cell.props?.width))
  expect(cells.length).toBe(2)
  expect(widths.size).toBe(1)
  expect([...widths][0]).toBeGreaterThanOrEqual('● conversation-analysis-extra'.length)
  expect(JSON.stringify(await ui.drawn())).toContain('conversation-analysis-extra')
  expect(JSON.stringify(await ui.drawn())).not.toContain('…')
  await ui.press({ key: 'agents' })
})

test('one very long name keeps its suffix and cannot widen every cell past the cap', async ($, on) => {
  engine(on)
  await command($ as never, 'reset')
  await offer($ as never, 'Explore')
  await offer($ as never, `local:${'x'.repeat(60)}-tail`)
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' })
  await ui.press({ key: 'agents' })
  const cells = cellsHolding((await ui.drawn()) as DrawnNode, 'agent-')
  expect(new Set(cells.map(cell => cell.props?.width)).size).toBe(1)
  expect(cells[0].props?.width).toBeLessThanOrEqual(34)
  expect(JSON.stringify(await ui.drawn())).toMatch(/…[^"]*-tail/)
  await ui.press({ key: 'agents' })
})

const DAY = 86_400_000

const DATES = () => {
  const now = Date.now()
  return { tdd: now - 2 * DAY, 'pstack:why': now - 30 * DAY }
}

async function openSkillsPanel($: { ui: { mount: (target: never) => Promise<any> } }) {
  const ui = await $.ui.mount({ ...BAR_TARGET, surface: 'desktop' } as never)
  await ui.press({ key: 'skills' })
  return ui
}

test('a skill run records its time and the skills listing shows its age', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  await skillText($ as never, 'pstack:tdd')
  expect(Date.now() - (world.store.lastUsed as Record<string, number>)['pstack:tdd']).toBeLessThan(5_000)
  const listing = (await command($ as never, 'skills')).text ?? ''
  expect(listing).toMatch(/pstack:tdd on · today/)
  expect(listing).toMatch(/pstack:why on · never seen/)
})

test('a stored date survives a later run of a different skill and is never replaced by an older one', async ($, on) => {
  const world = engine(on)
  const newest = Date.now() + 1_000_000
  world.store.lastUsed = { simplify: newest, tdd: 5 }
  await skillText($ as never, 'pstack:why')
  const stored = world.store.lastUsed as Record<string, number>
  expect(stored.simplify).toBe(newest)
  expect(stored['pstack:why']).toBeGreaterThan(0)
})

test('seed merges the newest dates from a backfill file and reports what was newer', async ($, on) => {
  const world = engine(on)
  const now = Date.now()
  world.store.lastUsed = { tdd: now - DAY }
  world.files['seed.json'] = JSON.stringify({ lastUsed: { tdd: now - 10 * DAY, simplify: now - 3 * DAY } })
  const answer = await command($ as never, 'seed seed.json')
  expect(answer.text).toBe('Seeded 2 names from seed.json. 1 newer than what was stored.')
  const stored = world.store.lastUsed as Record<string, number>
  expect(stored.tdd).toBe(now - DAY)
  expect(stored.simplify).toBe(now - 3 * DAY)
  expect((await command($ as never, 'seed nope.json')).text).toMatch(/^Could not read nope.json/)
  world.files['bad.json'] = '{"lastUsed": {"tdd": "soon"}}'
  expect((await command($ as never, 'seed bad.json')).text).toMatch(/holds no lastUsed dates/)
})

test('sorting by recent groups the skills by age and the stale button turns off only dated old skills', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  world.files['dates.json'] = JSON.stringify({ lastUsed: DATES() })
  await command($ as never, 'seed dates.json')
  const ui = await openSkillsPanel($ as never)
  await ui.press({ key: 'skills-sort' })
  const drawn = JSON.stringify(await ui.drawn())
  expect(drawn).toContain('used in the last 14 days')
  expect(drawn).toContain('unused 14+ days')
  expect(drawn).toContain('never seen')
  expect(drawn).toContain('tdd 2d')
  expect((await ui.find({ key: 'skills-turn-off-stale' }))?.text).toBe('turn off unused 14d+ (1)')
  await ui.press({ key: 'skills-turn-off-stale' })
  expect(world.toasts).toContain('1 skill off for this session.')
  expect(await skillText($ as never, 'pstack:why')).toMatch(/turned off/)
  expect(await skillText($ as never, 'simplify')).toBe('skill body')
  expect(await skillText($ as never, 'pstack:tdd')).toBe('skill body')
  expect((await ui.find({ key: 'skills-turn-off-stale' }))?.text).toBe('turn off unused 14d+ (0)')
  await ui.press({ key: 'skills' })
})

test('dates stored by an earlier session show in the skills listing and the panel without a seed', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  world.store.lastUsed = { tdd: Date.now() - 4 * DAY }
  expect((await command($ as never, 'skills')).text).toMatch(/pstack:tdd on · 4d ago/)
  const ui = await openSkillsPanel($ as never)
  await ui.press({ key: 'skills-sort' })
  expect(JSON.stringify(await ui.drawn())).toContain('pstack:tdd 4d')
  await ui.press({ key: 'skills' })
})

test('a refused skill run does not count as a use', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  await command($ as never, 'skill pstack:why off')
  expect(await skillText($ as never, 'pstack:why')).toMatch(/turned off/)
  expect((world.store.lastUsed as Record<string, number> | undefined)?.['pstack:why']).toBeUndefined()
  expect(await skillText($ as never, 'pstack:tdd')).toBe('skill body')
  expect((world.store.lastUsed as Record<string, number>)['pstack:tdd']).toBeGreaterThan(0)
})

test('the unused-after menu offers 14, 28 and 56 days and the stale count follows it', async ($, on) => {
  const world = engine(on)
  await command($ as never, 'reset')
  const now = Date.now()
  world.files['dates.json'] = JSON.stringify({ lastUsed: { tdd: now - 2 * DAY, simplify: now - 20 * DAY, 'pstack:why': now - 30 * DAY } })
  await command($ as never, 'seed dates.json')
  const ui = await openSkillsPanel($ as never)
  const menu = await ui.find({ key: 'skills-stale-days' })
  expect(menu?.props.options.map((option: { value: string }) => option.value)).toEqual(['14', '28', '56'])
  expect(menu?.props.value).toBe('14')
  const staleLabel = async () => (await ui.find({ key: 'skills-turn-off-stale' }))?.text
  expect(await staleLabel()).toBe('turn off unused 14d+ (2)')
  await ui.select({ key: 'skills-stale-days', value: '28' })
  expect(await staleLabel()).toBe('turn off unused 28d+ (1)')
  await ui.select({ key: 'skills-stale-days', value: '56' })
  expect(await staleLabel()).toBe('turn off unused 56d+ (0)')
  await ui.select({ key: 'skills-stale-days', value: '28' })
  await ui.press({ key: 'skills-turn-off-stale' })
  expect(await skillText($ as never, 'pstack:why')).toMatch(/turned off/)
  expect(await skillText($ as never, 'simplify')).toBe('skill body')
  await ui.press({ key: 'skills' })
})
