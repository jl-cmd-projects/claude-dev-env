export type Switch = 'on' | 'off'

export type Family = 'opus' | 'sonnet' | 'haiku' | 'fable'

export type Effort = 'inherit' | 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export type OffAction = 'move' | 'deny'

export type Settings = {
  opus: Switch
  fable: Switch
  sonnet: Switch
  haiku: Switch
  defaultModel: Family
  effort: Effort
  offAction: OffAction
  applyToRunning: Switch
}

export type AgentSwitches = Readonly<Record<string, Switch>>

export type Kind = 'agents' | 'skills'

export type SessionOverrides = Partial<Settings> & { agents?: AgentSwitches; skills?: AgentSwitches }

export type LastUsed = Readonly<Record<string, number>>

export type PinnedEfforts = Readonly<Record<string, Effort>>

declare module 'claude-code' {
  interface PluginState {
    'subagent-models': {
      overrides: SessionOverrides
      offeredAgents: readonly string[]
      pinnedEfforts: PinnedEfforts
      isBarOpen: boolean
      isAgentsOpen: boolean
      isSkillsOpen: boolean
      knownSkills: readonly string[]
      lastUsed: LastUsed
      isSortedByRecent: boolean
    }
  }
}
