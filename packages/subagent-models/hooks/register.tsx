import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register, StateDollar } from 'claude-code'

import type { AgentSwitches, Effort, Family, PinnedEfforts, SessionOverrides, Settings, Switch } from '../types'

const PLUGIN = 'subagent-models'

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

const isBarOpen = atom({ plugin: 'subagent-models', key: 'isBarOpen' } as const, true)

const AGENTS_SUMMARY = '__summary'

const MORE_SUMMARY = '__more'

const ON_MARK = '●'

const OFF_MARK = '○'

const ICON_MARK = '◈'

const ACCENT = '#7aa2f7'

const MINIMIZE_MARK = '▾'

const EXPAND_MARK = '▴'

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


async function toastAfter($: EngineInterface, action: Promise<string>) {
  $.ui.toast(await action)
}

const USAGE = `Usage: /${PLUGIN} [<field> <value> | agents | agent <type> on|off | bar | apply | save | reset]. Fields: ${ALL_FIELDS.join(', ')}.`

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
      if (word === 'bar') {
        const isOpen = await update($, isBarOpen, current => !current)
        return { text: isOpen ? 'Subagent bar expanded.' : 'Subagent bar minimized.' }
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.surface === 'mobile' || !(await read($, isBarOpen))) return next(e)
    const { Box, Text, Button, Select } = $.ui.resolve(e)
    const state = await sessionState($, defaults)
    const { settings } = state
    const allAgents = knownAgentsOf(state, await read($, offeredAgents), defaults)
    const turnedOffCount = allAgents.filter(agent => state.agentSwitchOf(agent) === 'off').length
    const runningCount = (await runningAgentIdsOf($)).length
    const optionsOf = (field: keyof Settings) => (ALL_CHOICES[field] as readonly string[]).map(choice => ({ value: choice }))

    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={2} paddingY={1} gap={1}>
        <Box flexDirection="row" flexWrap="wrap" columnGap={3} rowGap={1} alignItems="center" justifyContent="space-between">
          <Box flexDirection="row" flexWrap="wrap" columnGap={2} rowGap={1} alignItems="center">
            <Text bold color={ACCENT}>{`${ICON_MARK} Subagents`}</Text>
            <Text dimColor>models</Text>
            {ALL_FAMILIES.map(family => (
              <Button
                key={`model-${family}`}
                variant={settings[family] === 'on' ? 'primary' : 'secondary'}
                onPress={() => toastAfter($, setField($, defaults, family, flipped(settings[family])))}
              >
                {`${settings[family] === 'on' ? ON_MARK : OFF_MARK} ${family}`}
              </Button>
            ))}
          </Box>
          <Box flexDirection="row" columnGap={2} alignItems="center">
            <Select
              key="more"
              options={[
                { value: MORE_SUMMARY, label: 'more' },
                { value: 'save', label: 'save as defaults' },
                { value: 'reset', label: 'reset session' },
              ]}
              value={MORE_SUMMARY}
              onSelect={choice => {
                if (choice === 'save') void toastAfter($, saveDefaults($, defaults))
                if (choice === 'reset') void toastAfter($, resetSession($, defaults))
              }}
            />
            <Button key="minimize" dimColor onPress={() => update($, isBarOpen, () => false)}>
              {`${MINIMIZE_MARK} minimize`}
            </Button>
          </Box>
        </Box>
        <Box flexDirection="row" flexWrap="wrap" columnGap={4} rowGap={1} alignItems="center">
          <Select
            key="defaultModel"
            label="default"
            options={optionsOf('defaultModel')}
            value={settings.defaultModel}
            onSelect={choice => toastAfter($, setField($, defaults, 'defaultModel', choice))}
          />
          <Select
            key="effort"
            label="effort"
            options={optionsOf('effort')}
            value={settings.effort}
            onSelect={choice => toastAfter($, setField($, defaults, 'effort', choice))}
          />
          <Select
            key="offAction"
            label="off models"
            options={optionsOf('offAction')}
            value={settings.offAction}
            onSelect={choice => toastAfter($, setField($, defaults, 'offAction', choice))}
          />
          <Select
            key="agents"
            label="agents"
            options={[
              { value: AGENTS_SUMMARY, label: turnedOffCount === 0 ? 'all on' : `${turnedOffCount} off` },
              ...allAgents.map(agent => ({ value: agent, label: `${agent}: ${state.agentSwitchOf(agent)}` })),
            ]}
            value={AGENTS_SUMMARY}
            onSelect={agent => {
              if (agent !== AGENTS_SUMMARY) void toastAfter($, setAgent($, defaults, agent, flipped(state.agentSwitchOf(agent))))
            }}
          />
          <Select
            key="applyToRunning"
            label={`running ${runningCount}`}
            options={[
              { value: 'on', label: 'follow effort' },
              { value: 'off', label: 'keep start effort' },
            ]}
            value={settings.applyToRunning}
            onSelect={choice => toastAfter($, setField($, defaults, 'applyToRunning', choice))}
          />
          <Button key="apply" onPress={() => toastAfter($, applyNow($, defaults))}>
            apply now
          </Button>
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'SessionMode' }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const { settings, sessionOverrides } = await sessionState($, defaults)
    const isOpen = await read($, isBarOpen)
    const sessionMark = Object.keys(sessionOverrides).length > 0 ? '*' : ''
    return (
      <Box flexDirection="row" columnGap={2}>
        <Button key="pill" onPress={() => update($, isBarOpen, current => !current)}>
          {`${ICON_MARK} ${settings.defaultModel}/${settings.effort}${sessionMark} ${isOpen ? MINIMIZE_MARK : EXPAND_MARK}`}
        </Button>
        <Text dimColor>{e.props.modes.join(' & ')}</Text>
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
