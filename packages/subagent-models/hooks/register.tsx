import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register, StateDollar } from 'claude-code'

import type { AgentSwitches, Effort, Family, PinnedEfforts, SessionOverrides, Settings, Switch } from '../types'

const PLUGIN = 'subagent-models'

const PANE = 'subagent-models'

const ALL_CHOICES: { readonly [Field in keyof Settings]: readonly Settings[Field][] } = {
  opus: ['on', 'off'],
  fable: ['on', 'off'],
  sonnet: ['on', 'off'],
  haiku: ['on', 'off'],
  defaultModel: ['opus', 'sonnet', 'haiku', 'fable'],
  effort: ['inherit', 'low', 'medium', 'high', 'xhigh', 'max'],
  offAction: ['move', 'deny'],
  applyToRunning: ['on', 'off'],
}

const ALL_FIELDS = Object.keys(ALL_CHOICES) as (keyof Settings)[]

const ALL_FAMILIES: readonly Family[] = ['opus', 'sonnet', 'haiku', 'fable']

const ALL_SWITCHES: readonly Switch[] = ['on', 'off']

const overrides = atom({ plugin: 'subagent-models', key: 'overrides' } as const, {} as SessionOverrides)

const offeredAgents = atom({ plugin: 'subagent-models', key: 'offeredAgents' } as const, [] as readonly string[])

const pinnedEfforts = atom({ plugin: 'subagent-models', key: 'pinnedEfforts' } as const, {} as PinnedEfforts)

type Defaults = { settings: Settings; agents: AgentSwitches }

type State = { sessionOverrides: SessionOverrides; settings: Settings; agentSwitchOf: (agent: string) => Switch }

function familyOf(model: string | undefined): Family | undefined {
  if (model === undefined) return undefined
  const normalized = model.trim().toLowerCase()
  return ALL_FAMILIES.find(family => normalized === family || normalized.startsWith(`claude-${family}`))
}

function isField(name: string): name is keyof Settings {
  return (ALL_FIELDS as string[]).includes(name)
}

function isFamily(name: string): name is Family {
  return (ALL_FAMILIES as string[]).includes(name)
}

function isSwitch(value: string): value is Switch {
  return (ALL_SWITCHES as string[]).includes(value)
}

function isAllowed(settings: Settings, family: Family | undefined): boolean {
  return family === undefined || family === settings.defaultModel || settings[family] === 'on'
}

function flipped(value: Switch): Switch {
  return value === 'on' ? 'off' : 'on'
}

function agentSwitchesOf(text: string): AgentSwitches {
  return Object.fromEntries(text.split(',').map(agent => agent.trim()).filter(Boolean).map(agent => [agent, 'off' as Switch]))
}

function turnedOffAgentsOf(defaults: AgentSwitches, sessionAgents: AgentSwitches): string[] {
  const merged = { ...defaults, ...sessionAgents }
  return Object.keys(merged).filter(agent => merged[agent] === 'off').sort()
}

function knownAgentsOf(state: State, allOffered: readonly string[], defaults: Defaults): string[] {
  return [...new Set([...allOffered, ...turnedOffAgentsOf(defaults.agents, state.sessionOverrides.agents ?? {})])].sort()
}

function statusOf(settings: Settings, sessionOverrides: SessionOverrides): string {
  const sessionMark = Object.keys(sessionOverrides).length > 0 ? ' (session)' : ''
  return `subagents: ${settings.defaultModel}/${settings.effort}${sessionMark}`
}

function denyTextOf(model: string, settings: Settings): string {
  const effortAsk = settings.effort === 'inherit' ? '' : ` and ask for ${settings.effort} effort in the brief`
  return `Subagent model ${model} is turned off. Spawn subagents on ${settings.defaultModel}${effortAsk}.`
}

function listingOf(settings: Settings, sessionOverrides: SessionOverrides, defaults: Defaults): string {
  const fieldLines = ALL_FIELDS.map(field => `${field} ${settings[field]}${field in sessionOverrides ? ' (this session)' : ''}`)
  const turnedOff = turnedOffAgentsOf(defaults.agents, sessionOverrides.agents ?? {})
  const agentMark = sessionOverrides.agents === undefined ? '' : ' (this session)'
  return [...fieldLines, `agents off: ${turnedOff.length > 0 ? turnedOff.join(', ') : 'none'}${agentMark}`].join('\n')
}

function agentListingOf(state: State, allOffered: readonly string[], defaults: Defaults): string {
  const allAgents = knownAgentsOf(state, allOffered, defaults)
  if (allAgents.length === 0) return 'No agent types offered yet in this session.'
  return allAgents
    .map(agent => `${agent} ${state.agentSwitchOf(agent)}${state.sessionOverrides.agents?.[agent] === undefined ? '' : ' (this session)'}`)
    .join('\n')
}

function refusalOf(field: keyof Settings, value: string, settings: Settings): string | undefined {
  if (isFamily(field) && value === 'off' && settings.defaultModel === field) {
    return `${field} is the default model. Pick another defaultModel before turning ${field} off.`
  }
  if (field === 'defaultModel' && isFamily(value) && settings[value] === 'off') {
    return `${value} is turned off. Turn ${value} on before making it the default model.`
  }
  return undefined
}

async function sessionState($: StateDollar, defaults: Defaults): Promise<State> {
  const sessionOverrides = await read($, overrides)
  const { agents: sessionAgents = {}, ...sessionSettings } = sessionOverrides
  const settings = { ...defaults.settings, ...sessionSettings } as Settings
  const agentSwitchOf = (agent: string): Switch => sessionAgents[agent] ?? defaults.agents[agent] ?? 'on'
  return { sessionOverrides, settings, agentSwitchOf }
}

async function showStatus($: EngineInterface, defaults: Defaults) {
  const { settings, sessionOverrides } = await sessionState($, defaults)
  $.ui.status(statusOf(settings, sessionOverrides))
}

async function setField($: EngineInterface, defaults: Defaults, field: keyof Settings, value: string): Promise<string> {
  const allChoices = ALL_CHOICES[field] as readonly string[]
  if (!allChoices.includes(value)) return `${field} takes ${allChoices.join(', ')}.`
  const { settings } = await sessionState($, defaults)
  const refusal = refusalOf(field, value, settings)
  if (refusal !== undefined) return refusal
  await update($, overrides, current => ({ ...current, [field]: value }))
  await showStatus($, defaults)
  return `${field} ${value} for this session.`
}

async function setAgent($: EngineInterface, defaults: Defaults, agent: string, agentSwitch: Switch): Promise<string> {
  await update($, overrides, current => ({ ...current, agents: { ...current.agents, [agent]: agentSwitch } }))
  await showStatus($, defaults)
  return `agent ${agent} ${agentSwitch} for this session.`
}

async function resetSession($: EngineInterface, defaults: Defaults): Promise<string> {
  await update($, overrides, () => ({}))
  await showStatus($, defaults)
  return 'Session values cleared. The /config defaults apply again.'
}

async function saveDefaults($: EngineInterface, defaults: Defaults): Promise<string> {
  const { settings, sessionOverrides } = await sessionState($, defaults)
  const { agents: sessionAgents, ...sessionSettings } = sessionOverrides
  for (const field of Object.keys(sessionSettings) as (keyof Settings)[]) {
    await $.config.set({ key: `${PLUGIN}.${field}`, value: settings[field] })
  }
  if (sessionAgents !== undefined) {
    await $.config.set({ key: `${PLUGIN}.disabledAgents`, value: turnedOffAgentsOf(defaults.agents, sessionAgents).join(', ') })
  }
  return `Saved as defaults:\n${listingOf(settings, {}, { ...defaults, agents: { ...defaults.agents, ...sessionAgents } })}`
}

async function runningAgentIdsOf($: EngineInterface): Promise<string[]> {
  return (await $.agent.list()).filter(agent => agent.status === 'running').map(agent => agent.id)
}

async function applyNow($: EngineInterface, defaults: Defaults): Promise<string> {
  const { settings } = await sessionState($, defaults)
  const allRunning = await runningAgentIdsOf($)
  await update($, pinnedEfforts, current => ({ ...current, ...Object.fromEntries(allRunning.map(agentId => [agentId, settings.effort])) }))
  return `effort ${settings.effort} applied to ${allRunning.length} running subagent${allRunning.length === 1 ? '' : 's'}.`
}

async function effortFor($: StateDollar, settings: Settings, agentId: string, requestEffort: Effort | undefined) {
  if (requestEffort === undefined) return undefined
  const pinned = (await read($, pinnedEfforts))[agentId]
  const isFollowingSettings = settings.applyToRunning === 'on' || pinned === undefined
  if (isFollowingSettings && pinned !== settings.effort) {
    await update($, pinnedEfforts, current => ({ ...current, [agentId]: settings.effort }))
  }
  const target = isFollowingSettings || pinned === undefined ? settings.effort : pinned
  return target === 'inherit' ? requestEffort : target
}

async function openPicker($: EngineInterface) {
  await $.ui.open({ id: PANE, title: 'Subagent models', focus: true })
}

async function toastAfter($: EngineInterface, action: Promise<string>) {
  $.ui.toast(await action)
}

const USAGE = `Usage: /${PLUGIN} [<field> <value> | agents | agent <type> on|off | picker | apply | save | reset]. Fields: ${ALL_FIELDS.join(', ')}.`

export const register: Register = (on, options: PluginOptions) => {
  const defaults: Defaults = {
    settings: Object.fromEntries(ALL_FIELDS.map(field => [field, String(options[field])])) as Settings,
    agents: agentSwitchesOf(String(options.disabledAgents ?? '')),
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: PLUGIN,
      description: 'Show or change which models and agent types subagents may run as, and their effort, for this session',
    })
    await showStatus($, defaults)
    return next(e)
  })

  on('command.run', { command: PLUGIN }, async ($, e) => {
    const [word = '', value, ...rest] = e.args.trim().split(/\s+/).filter(Boolean)
    const state = await sessionState($, defaults)
    if (word === '') return { text: listingOf(state.settings, state.sessionOverrides, defaults) }
    if (value === undefined) {
      if (word === 'reset') return { text: await resetSession($, defaults) }
      if (word === 'save') return { text: await saveDefaults($, defaults) }
      if (word === 'apply') return { text: await applyNow($, defaults) }
      if (word === 'agents') return { text: agentListingOf(state, await read($, offeredAgents), defaults) }
      if (word === 'picker') {
        await openPicker($)
        return { text: 'Subagent models picker opened.' }
      }
    }
    if (word === 'agent') {
      const [agentSwitch, ...extra] = rest
      if (value === undefined || agentSwitch === undefined || !isSwitch(agentSwitch) || extra.length > 0) return { text: USAGE }
      return { text: await setAgent($, defaults, value, agentSwitch) }
    }
    if (!isField(word) || value === undefined || rest.length > 0) return { text: USAGE }
    return { text: await setField($, defaults, word, value) }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const state = await sessionState($, defaults)
    const { settings } = state
    const allAgents = knownAgentsOf(state, await read($, offeredAgents), defaults)
    const runningCount = (await runningAgentIdsOf($)).length
    const choiceRow = (field: keyof Settings, label: string) => (
      <Box flexDirection="column">
        <Text bold>{`${label}: ${settings[field]}`}</Text>
        <Box flexDirection="row" flexWrap="wrap" columnGap={1}>
          {(ALL_CHOICES[field] as readonly string[]).map(choice => (
            <Button
              key={`${field}-${choice}`}
              variant={settings[field] === choice ? 'primary' : 'secondary'}
              onPress={() => toastAfter($, setField($, defaults, field, choice))}
            >
              {choice}
            </Button>
          ))}
        </Box>
      </Box>
    )

    return (
      <Box flexDirection="column" gap={1}>
        <Text>{statusOf(settings, state.sessionOverrides)}</Text>
        <Box flexDirection="column">
          <Text bold>Models</Text>
          <Box flexDirection="row" flexWrap="wrap" columnGap={1}>
            {ALL_FAMILIES.map(family => (
              <Button
                key={`model-${family}`}
                variant={settings[family] === 'on' ? 'primary' : 'secondary'}
                onPress={() => toastAfter($, setField($, defaults, family, flipped(settings[family])))}
              >
                {`${family} ${settings[family]}`}
              </Button>
            ))}
          </Box>
        </Box>
        {choiceRow('defaultModel', 'Default model')}
        {choiceRow('effort', 'Effort')}
        {choiceRow('offAction', 'When a spawn names a turned-off model')}
        <Box flexDirection="column">
          <Text bold>Agent types</Text>
          {allAgents.length === 0 && <Text dimColor>No agent types offered yet in this session.</Text>}
          <Box flexDirection="row" flexWrap="wrap" columnGap={1}>
            {allAgents.map(agent => (
              <Button
                key={`agent-${agent}`}
                variant={state.agentSwitchOf(agent) === 'on' ? 'primary' : 'secondary'}
                onPress={() => toastAfter($, setAgent($, defaults, agent, flipped(state.agentSwitchOf(agent))))}
              >
                {`${agent} ${state.agentSwitchOf(agent)}`}
              </Button>
            ))}
          </Box>
        </Box>
        <Box flexDirection="column">
          <Text bold>{`Running subagents: ${runningCount}`}</Text>
          <Box flexDirection="row" flexWrap="wrap" columnGap={1}>
            <Button
              key="applyToRunning"
              variant={settings.applyToRunning === 'on' ? 'primary' : 'secondary'}
              onPress={() => toastAfter($, setField($, defaults, 'applyToRunning', flipped(settings.applyToRunning)))}
            >
              {`Effort changes reach running subagents: ${settings.applyToRunning}`}
            </Button>
            <Button key="apply" onPress={() => toastAfter($, applyNow($, defaults))}>
              Apply effort to running subagents now
            </Button>
          </Box>
        </Box>
        <Box flexDirection="row" columnGap={1}>
          <Button key="save" onPress={() => toastAfter($, saveDefaults($, defaults))}>
            Save as defaults
          </Button>
          <Button key="reset" onPress={() => toastAfter($, resetSession($, defaults))}>
            Reset session
          </Button>
        </Box>
      </Box>
    )
  })

  on('agent.offer', async ($, e, next) => {
    const allOffered = await read($, offeredAgents)
    if (!allOffered.includes(e.agent)) await update($, offeredAgents, current => [...current, e.agent])
    const { agentSwitchOf } = await sessionState($, defaults)
    if (agentSwitchOf(e.agent) === 'off') return { isOffered: false }
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    if (e.fork) return next(e)
    const { settings, agentSwitchOf } = await sessionState($, defaults)
    if (agentSwitchOf(e.subagentType) === 'off') return { deny: `Subagent type ${e.subagentType} is turned off. Pick another subagent_type.` }
    if (e.model === undefined || isAllowed(settings, familyOf(e.model))) return next(e)
    if (settings.offAction === 'deny') return { deny: denyTextOf(e.model, settings) }
    return next({ ...e, model: settings.defaultModel })
  })

  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined) return yield* next(e)
    const { settings } = await sessionState($, defaults)
    const model = isAllowed(settings, familyOf(e.model)) ? e.model : settings.defaultModel
    const effort = await effortFor($, settings, e.agentId, e.effort)
    return yield* next({ ...e, model, effort })
  })
}
