import { atom, read, update } from 'claude-code'
import type { PluginOptions, Register, StateDollar } from 'claude-code'

import type { AgentSwitches, Family, SessionOverrides, Settings, Switch } from '../types'

const PLUGIN = 'subagent-models'

const ALL_CHOICES: { readonly [Field in keyof Settings]: readonly Settings[Field][] } = {
  opus: ['on', 'off'],
  fable: ['on', 'off'],
  sonnet: ['on', 'off'],
  haiku: ['on', 'off'],
  defaultModel: ['opus', 'sonnet', 'haiku', 'fable'],
  effort: ['inherit', 'low', 'medium', 'high', 'xhigh', 'max'],
  offAction: ['move', 'deny'],
}

const ALL_FIELDS = Object.keys(ALL_CHOICES) as (keyof Settings)[]

const ALL_FAMILIES: readonly Family[] = ['opus', 'sonnet', 'haiku', 'fable']

const ALL_SWITCHES: readonly Switch[] = ['on', 'off']

const overrides = atom({ plugin: 'subagent-models', key: 'overrides' } as const, {} as SessionOverrides)

const offeredAgents = atom({ plugin: 'subagent-models', key: 'offeredAgents' } as const, [] as readonly string[])

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

function agentSwitchesOf(text: string): AgentSwitches {
  return Object.fromEntries(text.split(',').map(agent => agent.trim()).filter(Boolean).map(agent => [agent, 'off' as Switch]))
}

function turnedOffAgentsOf(defaults: AgentSwitches, sessionAgents: AgentSwitches): string[] {
  const merged = { ...defaults, ...sessionAgents }
  return Object.keys(merged).filter(agent => merged[agent] === 'off').sort()
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
  const allAgents = [...new Set([...allOffered, ...turnedOffAgentsOf(defaults.agents, state.sessionOverrides.agents ?? {})])].sort()
  if (allAgents.length === 0) return 'No agent types offered yet in this session.'
  return allAgents
    .map(agent => `${agent} ${state.agentSwitchOf(agent)}${state.sessionOverrides.agents?.[agent] === undefined ? '' : ' (this session)'}`)
    .join('\n')
}

async function sessionState($: StateDollar, defaults: Defaults): Promise<State> {
  const sessionOverrides = await read($, overrides)
  const { agents: sessionAgents = {}, ...sessionSettings } = sessionOverrides
  const settings = { ...defaults.settings, ...sessionSettings } as Settings
  const agentSwitchOf = (agent: string): Switch => sessionAgents[agent] ?? defaults.agents[agent] ?? 'on'
  return { sessionOverrides, settings, agentSwitchOf }
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

const USAGE = `Usage: /${PLUGIN} [<field> <value> | agents | agent <type> on|off | save | reset]. Fields: ${ALL_FIELDS.join(', ')}.`

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
    const { settings, sessionOverrides } = await sessionState($, defaults)
    $.ui.status(statusOf(settings, sessionOverrides))
    return next(e)
  })

  on('command.run', { command: PLUGIN }, async ($, e) => {
    const [word = '', value, ...rest] = e.args.trim().split(/\s+/).filter(Boolean)
    const state = await sessionState($, defaults)
    const { settings, sessionOverrides } = state
    if (word === '') return { text: listingOf(settings, sessionOverrides, defaults) }
    if (word === 'reset' && value === undefined) {
      await update($, overrides, () => ({}))
      $.ui.status(statusOf(defaults.settings, {}))
      return { text: 'Session values cleared. The /config defaults apply again.' }
    }
    if (word === 'save' && value === undefined) {
      const { agents: sessionAgents, ...sessionSettings } = sessionOverrides
      for (const field of Object.keys(sessionSettings) as (keyof Settings)[]) {
        await $.config.set({ key: `${PLUGIN}.${field}`, value: settings[field] })
      }
      if (sessionAgents !== undefined) {
        await $.config.set({ key: `${PLUGIN}.disabledAgents`, value: turnedOffAgentsOf(defaults.agents, sessionAgents).join(', ') })
      }
      return { text: `Saved as defaults:\n${listingOf(settings, {}, { ...defaults, agents: { ...defaults.agents, ...sessionAgents } })}` }
    }
    if (word === 'agents' && value === undefined) return { text: agentListingOf(state, await read($, offeredAgents), defaults) }
    if (word === 'agent') {
      const [agentSwitch, ...extra] = rest
      if (value === undefined || agentSwitch === undefined || !isSwitch(agentSwitch) || extra.length > 0) return { text: USAGE }
      await update($, overrides, current => ({ ...current, agents: { ...current.agents, [value]: agentSwitch } }))
      return { text: `agent ${value} ${agentSwitch} for this session.` }
    }
    if (!isField(word) || value === undefined || rest.length > 0) return { text: USAGE }
    const allChoices = ALL_CHOICES[word] as readonly string[]
    if (!allChoices.includes(value)) return { text: `${word} takes ${allChoices.join(', ')}.` }
    const refusal = refusalOf(word, value, settings)
    if (refusal !== undefined) return { text: refusal }
    const nextOverrides = await update($, overrides, current => ({ ...current, [word]: value }))
    const { agents: _sessionAgents, ...nextSettings } = nextOverrides
    $.ui.status(statusOf({ ...defaults.settings, ...nextSettings } as Settings, nextOverrides))
    return { text: `${word} ${value} for this session.` }
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
    const effort = settings.effort === 'inherit' || e.effort === undefined ? e.effort : settings.effort
    return yield* next({ ...e, model, effort })
  })
}
