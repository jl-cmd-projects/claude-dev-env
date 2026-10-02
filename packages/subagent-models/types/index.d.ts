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
}

export type AgentSwitches = Readonly<Record<string, Switch>>

export type SessionOverrides = Partial<Settings> & { agents?: AgentSwitches }

declare module 'claude-code' {
  interface PluginState {
    'subagent-models': { overrides: SessionOverrides; offeredAgents: readonly string[] }
  }
}
