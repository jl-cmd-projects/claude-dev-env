import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register, StateDollar } from 'claude-code'

import type { AgentSwitches, Effort, Family, Kind, LastUsed, PinnedEfforts, SessionOverrides, Settings, Switch } from '../types'

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

const ALL_KINDS: readonly Kind[] = ['agents', 'skills']

const KIND_DETAILS: { readonly [K in Kind]: { word: string; noun: string; title: string; core: string; empty: string; configKey: string } } = {
  agents: {
    word: 'agent',
    noun: 'agent type',
    title: 'Agent types',
    core: 'core',
    empty: 'No agent types offered yet. They appear after the first spawn.',
    configKey: 'disabledAgents',
  },
  skills: {
    word: 'skill',
    noun: 'skill',
    title: 'Skills',
    core: 'local',
    empty: 'No skills listed yet. Press skills again once the session has started.',
    configKey: 'disabledSkills',
  },
}

const overrides = atom({ plugin: 'subagent-models', key: 'overrides' } as const, {} as SessionOverrides)

const offeredAgents = atom({ plugin: 'subagent-models', key: 'offeredAgents' } as const, [] as readonly string[])

const knownSkills = atom({ plugin: 'subagent-models', key: 'knownSkills' } as const, [] as readonly string[])

const pinnedEfforts = atom({ plugin: 'subagent-models', key: 'pinnedEfforts' } as const, {} as PinnedEfforts)

const isBarOpen = atom({ plugin: 'subagent-models', key: 'isBarOpen' } as const, true)

const isAgentsOpen = atom({ plugin: 'subagent-models', key: 'isAgentsOpen' } as const, false)

const isSkillsOpen = atom({ plugin: 'subagent-models', key: 'isSkillsOpen' } as const, false)

const lastUsedDates = atom({ plugin: 'subagent-models', key: 'lastUsed' } as const, {} as LastUsed)

const isSortedByRecent = atom({ plugin: 'subagent-models', key: 'isSortedByRecent' } as const, false)

const LAST_USED_KEY = 'lastUsed'

const DAY_MS = 86_400_000

const DEFAULT_STALE_DAYS = 14

const BACKFILL_COMMAND = 'node packages/subagent-models/scripts/backfill-last-used.mjs --out <file>'

const MORE_SUMMARY = '__more'

const ON_MARK = '●'

const OFF_MARK = '○'

const ICON_MARK = '◈'

const ACCENT = '#7aa2f7'

const MINIMIZE_MARK = '▾'

const EXPAND_MARK = '▴'

const SIDE_OPEN_MARK = '◂'

const SIDE_CLOSED_MARK = '▸'

const MIN_CELL_CHARS = 14

const MAX_CELL_CHARS = 34

const CELL_PADDING = 2

const COLUMN_GAP = 2

const BAR_COLUMNS = 4

const BAR_CELL_CHARS = 18

const BAR_COLUMN_GAP = 1

const INLINE_LIMIT = 16

const PANE_IDS: { readonly [K in Kind]: string } = { agents: 'subagent-agents', skills: 'subagent-skills' }

type Ui = ReturnType<EngineInterface['ui']['resolve']>

type Defaults = { settings: Settings; switches: Record<Kind, AgentSwitches> }

type State = {
  sessionOverrides: SessionOverrides
  settings: Settings
  merged: Record<Kind, AgentSwitches>
  switchOf: (kind: Kind, name: string) => Switch
}

type Group = { title: string; items: { name: string; label: string }[] }

type SkillsView = { isRecent: boolean; staleNames: string[]; staleDays: number }

type PanelData = { state: State; kind: Kind; names: string[]; groups: Group[]; skillsView?: SkillsView }

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

function switchesOf(text: string): AgentSwitches {
  return Object.fromEntries(text.split(',').map(name => name.trim()).filter(Boolean).map(name => [name, 'off' as Switch]))
}

function turnedOffOf(merged: AgentSwitches): string[] {
  return Object.keys(merged).filter(name => merged[name] === 'off').sort()
}

function knownNamesOf(merged: AgentSwitches, allSeen: readonly string[]): string[] {
  return [...new Set([...allSeen, ...Object.keys(merged)])].sort()
}

function isSkillOff(merged: AgentSwitches, skill: string): boolean {
  if (merged[skill] !== undefined) return merged[skill] === 'off'
  return Object.entries(merged).some(([name, value]) => value === 'off' && (name.endsWith(`:${skill}`) || skill.endsWith(`:${name}`)))
}

function groupsOf(names: readonly string[], coreTitle: string): Group[] {
  const itemsByTitle = new Map<string, Group['items']>()
  for (const name of names) {
    const cut = name.indexOf(':')
    const title = cut === -1 ? coreTitle : name.slice(0, cut)
    const label = cut === -1 ? name : name.slice(cut + 1)
    itemsByTitle.set(title, [...(itemsByTitle.get(title) ?? []), { name, label }])
  }
  return [...itemsByTitle.entries()]
    .sort(([first], [second]) => (first === coreTitle ? -1 : second === coreTitle ? 1 : first.localeCompare(second)))
    .map(([title, items]) => ({ title, items }))
}

function isDates(value: unknown): value is LastUsed {
  return typeof value === 'object' && value !== null && !Array.isArray(value) && Object.values(value).every(when => typeof when === 'number' && Number.isFinite(when))
}

function mergedDates(first: LastUsed, second: LastUsed): LastUsed {
  const merged: Record<string, number> = { ...first }
  for (const [name, when] of Object.entries(second)) {
    if (when > (merged[name] ?? 0)) merged[name] = when
  }
  return merged
}

function lastUsedOf(lastUsed: LastUsed, skill: string): number | undefined {
  const dates = Object.entries(lastUsed)
    .filter(([name]) => name === skill || name.endsWith(`:${skill}`) || skill.endsWith(`:${name}`))
    .map(([, when]) => when)
  return dates.length === 0 ? undefined : Math.max(...dates)
}

function ageDaysOf(when: number, now: number): number {
  return Math.max(0, Math.floor((now - when) / DAY_MS))
}

function ageTextOf(when: number | undefined, now: number): string {
  if (when === undefined) return 'never seen'
  const days = ageDaysOf(when, now)
  return days === 0 ? 'today' : `${days}d ago`
}

function staleNamesOf(names: readonly string[], lastUsed: LastUsed, now: number, staleDays: number): string[] {
  return names.filter(name => {
    const when = lastUsedOf(lastUsed, name)
    return when !== undefined && ageDaysOf(when, now) > staleDays
  })
}

function recentGroupsOf(names: readonly string[], lastUsed: LastUsed, now: number, staleDays: number): Group[] {
  const dated = names.map(name => ({ name, when: lastUsedOf(lastUsed, name) }))
  const newestFirst = (first: { when?: number; name: string }, second: { when?: number; name: string }) =>
    (second.when ?? 0) - (first.when ?? 0) || first.name.localeCompare(second.name)
  const itemOf = ({ name, when }: { name: string; when?: number }) => ({
    name,
    label: when === undefined ? name : `${name} ${ageDaysOf(when, now)}d`,
  })
  const isFresh = ({ when }: { when?: number }) => when !== undefined && ageDaysOf(when, now) <= staleDays
  const isStale = ({ when }: { when?: number }) => when !== undefined && ageDaysOf(when, now) > staleDays
  return [
    { title: `used in the last ${staleDays} days`, items: dated.filter(isFresh).sort(newestFirst).map(itemOf) },
    { title: `unused ${staleDays}+ days`, items: dated.filter(isStale).sort(newestFirst).map(itemOf) },
    { title: 'never seen', items: dated.filter(({ when }) => when === undefined).sort(newestFirst).map(itemOf) },
  ].filter(group => group.items.length > 0)
}

function chipLabelOf(isOn: boolean, label: string): string {
  return `${isOn ? ON_MARK : OFF_MARK} ${label}`
}

function cellCharsOf(labels: readonly string[]): number {
  return Math.min(MAX_CELL_CHARS, Math.max(MIN_CELL_CHARS, ...labels.map(label => chipLabelOf(true, label).length)) + CELL_PADDING)
}

function fitLabelOf(label: string, cellChars: number): string {
  const room = cellChars - CELL_PADDING - chipLabelOf(true, '').length
  if (label.length <= room) return label
  const tail = Math.ceil((room - 1) * 0.6)
  return `${label.slice(0, room - 1 - tail)}…${label.slice(label.length - tail)}`
}

function cellOf(ui: Ui, key: string, cellChars: number, child: unknown) {
  const { Box } = ui
  return (
    <Box key={key} width={cellChars}>
      {child}
    </Box>
  )
}

function rowsOf<T>(items: readonly T[], size: number): T[][] {
  return Array.from({ length: Math.ceil(items.length / size) }, (_, index) => items.slice(index * size, (index + 1) * size))
}

function columnsFor(bodyColumns: number, cellChars: number): number {
  return Math.max(1, Math.floor((bodyColumns + COLUMN_GAP) / (cellChars + COLUMN_GAP)))
}

function denyTextOf(model: string, settings: Settings): string {
  const effortAsk = settings.effort === 'inherit' ? '' : ` and ask for ${settings.effort} effort in the brief`
  return `Subagent model ${model} is turned off. Spawn subagents on ${settings.defaultModel}${effortAsk}.`
}

function skillOffTextOf(skill: string): string {
  return `The ${skill} skill is turned off for this session. Do not follow it. Tell the user it is off and continue without it.`
}

function listingOf(settings: Settings, sessionOverrides: SessionOverrides, merged: Record<Kind, AgentSwitches>): string {
  const fieldLines = ALL_FIELDS.map(field => `${field} ${settings[field]}${field in sessionOverrides ? ' (this session)' : ''}`)
  const kindLines = [...ALL_KINDS].reverse().map(kind => {
    const turnedOff = turnedOffOf(merged[kind])
    const sessionMark = sessionOverrides[kind] === undefined ? '' : ' (this session)'
    return `${kind} off: ${turnedOff.length > 0 ? turnedOff.join(', ') : 'none'}${sessionMark}`
  })
  return [...fieldLines, ...kindLines].join('\n')
}

function kindListingOf(kind: Kind, state: State, allSeen: readonly string[], lastUsed?: LastUsed): string {
  const names = knownNamesOf(state.merged[kind], allSeen)
  if (names.length === 0) return KIND_DETAILS[kind].empty
  const now = Date.now()
  return names
    .map(name => {
      const sessionMark = state.sessionOverrides[kind]?.[name] === undefined ? '' : ' (this session)'
      const usedMark = lastUsed === undefined ? '' : ` · ${ageTextOf(lastUsedOf(lastUsed, name), now)}`
      return `${name} ${state.switchOf(kind, name)}${sessionMark}${usedMark}`
    })
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
  const { agents: sessionAgents = {}, skills: sessionSkills = {}, ...sessionSettings } = sessionOverrides
  const settings = { ...defaults.settings, ...sessionSettings } as Settings
  const merged = {
    agents: { ...defaults.switches.agents, ...sessionAgents },
    skills: { ...defaults.switches.skills, ...sessionSkills },
  }
  const switchOf = (kind: Kind, name: string): Switch => merged[kind][name] ?? 'on'
  return { sessionOverrides, settings, merged, switchOf }
}

async function setField($: EngineInterface, defaults: Defaults, field: keyof Settings, value: string): Promise<string> {
  const allChoices = ALL_CHOICES[field] as readonly string[]
  if (!allChoices.includes(value)) return `${field} takes ${allChoices.join(', ')}.`
  const { settings } = await sessionState($, defaults)
  const refusal = refusalOf(field, value, settings)
  if (refusal !== undefined) return refusal
  await update($, overrides, current => ({ ...current, [field]: value }))
  return `${field} ${value} for this session.`
}

async function setSwitch($: EngineInterface, kind: Kind, name: string, nameSwitch: Switch): Promise<string> {
  await update($, overrides, current => ({ ...current, [kind]: { ...current[kind], [name]: nameSwitch } }))
  return `${KIND_DETAILS[kind].word} ${name} ${nameSwitch} for this session.`
}

async function setAllSwitches($: EngineInterface, kind: Kind, names: readonly string[], nameSwitch: Switch): Promise<string> {
  await update($, overrides, current => ({
    ...current,
    [kind]: { ...current[kind], ...Object.fromEntries(names.map(name => [name, nameSwitch])) },
  }))
  return `${names.length} ${KIND_DETAILS[kind].noun}${names.length === 1 ? '' : 's'} ${nameSwitch} for this session.`
}

async function refreshSkills($: EngineInterface): Promise<void> {
  const usage = await $.session.usage({ breakdown: 'summary' })
  const listed = usage.context.breakdown?.skills?.skillFrontmatter ?? []
  const names = listed.map(skill => (skill.pluginName !== undefined && !skill.name.includes(':') ? `${skill.pluginName}:${skill.name}` : skill.name))
  await update($, knownSkills, current => [...new Set([...current, ...names])].sort())
}

async function loadLastUsed($: EngineInterface): Promise<void> {
  const stored = await $.store.get(LAST_USED_KEY)
  if (isDates(stored)) await update($, lastUsedDates, current => mergedDates(current, stored))
}

async function recordUse($: EngineInterface, skill: string): Promise<void> {
  const used = { [skill]: Date.now() }
  const stored = await $.store.get(LAST_USED_KEY)
  await $.store.set(LAST_USED_KEY, mergedDates(isDates(stored) ? stored : {}, used))
  await update($, lastUsedDates, current => mergedDates(current, used))
}

async function seedFrom($: EngineInterface, path: string): Promise<string> {
  let incoming: unknown
  try {
    incoming = JSON.parse(String(await $.fs.read(path))).lastUsed
  } catch {
    return `Could not read ${path} as JSON. Make it with: ${BACKFILL_COMMAND}`
  }
  if (!isDates(incoming) || Object.keys(incoming).length === 0) return `${path} holds no lastUsed dates. Make it with: ${BACKFILL_COMMAND}`
  const stored = await $.store.get(LAST_USED_KEY)
  const before = isDates(stored) ? stored : {}
  const newer = Object.keys(incoming).filter(name => incoming[name] > (before[name] ?? 0)).length
  const merged = mergedDates(before, incoming)
  await $.store.set(LAST_USED_KEY, merged)
  await update($, lastUsedDates, current => mergedDates(current, merged))
  return `Seeded ${Object.keys(incoming).length} names from ${path}. ${newer} newer than what was stored.`
}

async function panelDataOf($: StateDollar, defaults: Defaults, kind: Kind, staleDays: number): Promise<PanelData> {
  const state = await sessionState($, defaults)
  const names = await panelNamesOf($, defaults, kind)
  const { core } = KIND_DETAILS[kind]
  if (kind !== 'skills') return { state, kind, names, groups: groupsOf(names, core) }
  const lastUsed = await read($, lastUsedDates)
  const isRecent = await read($, isSortedByRecent)
  const now = Date.now()
  const staleNames = staleNamesOf(names, lastUsed, now, staleDays).filter(name => state.switchOf(kind, name) === 'on')
  const groups = isRecent ? recentGroupsOf(names, lastUsed, now, staleDays) : groupsOf(names, core)
  return { state, kind, names, groups, skillsView: { isRecent, staleNames, staleDays } }
}

async function panelNamesOf($: StateDollar, defaults: Defaults, kind: Kind): Promise<string[]> {
  const { merged } = await sessionState($, defaults)
  const allSeen = kind === 'agents' ? await read($, offeredAgents) : await read($, knownSkills)
  return knownNamesOf(merged[kind], allSeen)
}

async function isPanelOpenOf($: StateDollar, kind: Kind): Promise<boolean> {
  return kind === 'agents' ? read($, isAgentsOpen) : read($, isSkillsOpen)
}

async function setPanelOpen($: StateDollar, kind: Kind, isOpen: boolean): Promise<void> {
  if (kind === 'agents') await update($, isAgentsOpen, () => isOpen)
  else await update($, isSkillsOpen, () => isOpen)
}

async function togglePanel($: EngineInterface, defaults: Defaults, kind: Kind): Promise<void> {
  const wasOpen = await isPanelOpenOf($, kind)
  if (!wasOpen && kind === 'skills') await refreshSkills($)
  const isSide = (await panelNamesOf($, defaults, kind)).length > INLINE_LIMIT
  await setPanelOpen($, kind, !wasOpen)
  if (!isSide) return
  if (wasOpen) await $.ui.close({ id: PANE_IDS[kind] })
  else await $.ui.open({ id: PANE_IDS[kind], title: KIND_DETAILS[kind].title })
}

async function resetSession($: EngineInterface): Promise<string> {
  await update($, overrides, () => ({}))
  return 'Session values cleared. The /config defaults apply again.'
}

async function saveDefaults($: EngineInterface, defaults: Defaults): Promise<string> {
  const { settings, sessionOverrides, merged } = await sessionState($, defaults)
  const { agents: _sessionAgents, skills: _sessionSkills, ...sessionSettings } = sessionOverrides
  for (const field of Object.keys(sessionSettings) as (keyof Settings)[]) {
    await $.config.set({ key: `${PLUGIN}.${field}`, value: settings[field] })
  }
  for (const kind of ALL_KINDS) {
    if (sessionOverrides[kind] !== undefined) {
      await $.config.set({ key: `${PLUGIN}.${KIND_DETAILS[kind].configKey}`, value: turnedOffOf(merged[kind]).join(', ') })
    }
  }
  return `Saved as defaults:\n${listingOf(settings, {}, merged)}`
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

function panelOf($: EngineInterface, ui: Ui, data: PanelData, columnsOf: (cellChars: number) => number, hasTitle: boolean, debugText?: string) {
  const { Box, Text, Button } = ui
  const { state, kind, names, groups, skillsView } = data
  const { word, title, empty } = KIND_DETAILS[kind]
  const onCount = names.filter(name => state.switchOf(kind, name) === 'on').length
  const cellChars = cellCharsOf(groups.flatMap(group => group.items.map(item => item.label)))
  const columns = columnsOf(cellChars)
  return (
    <Box flexDirection="column" gap={1}>
      <Box flexDirection="row" flexWrap="wrap" columnGap={COLUMN_GAP} alignItems="center">
        {hasTitle && <Text bold color={ACCENT}>{title}</Text>}
        <Text dimColor>{`${onCount} of ${names.length} on`}</Text>
        <Button key={`${kind}-enable-all`} dimColor onPress={() => toastAfter($, setAllSwitches($, kind, names, 'on'))}>
          enable all
        </Button>
        <Button key={`${kind}-disable-all`} dimColor onPress={() => toastAfter($, setAllSwitches($, kind, names, 'off'))}>
          disable all
        </Button>
        {skillsView !== undefined && (
          <Button key="skills-sort" dimColor onPress={() => update($, isSortedByRecent, current => !current)}>
            {skillsView.isRecent ? 'sort: recent' : 'sort: name'}
          </Button>
        )}
        {skillsView !== undefined && (
          <Button key="skills-turn-off-stale" dimColor onPress={() => toastAfter($, setAllSwitches($, kind, skillsView.staleNames, 'off'))}>
            {`turn off unused ${skillsView.staleDays}d+ (${skillsView.staleNames.length})`}
          </Button>
        )}
        {debugText !== undefined && <Text dimColor>{debugText}</Text>}
      </Box>
      {names.length === 0 ? (
        <Text dimColor>{empty}</Text>
      ) : (
        groups.map(group => (
          <Box key={`group-${group.title}`} flexDirection="column" gap={1}>
            <Text dimColor>{group.title}</Text>
            {rowsOf(group.items, columns).map(row => (
              <Box key={`row-${row[0].name}`} flexDirection="row" columnGap={COLUMN_GAP}>
                {row.map(item =>
                  cellOf(
                    ui,
                    `cell-${word}-${item.name}`,
                    cellChars,
                    <Button
                      key={`${word}-${item.name}`}
                      variant={state.switchOf(kind, item.name) === 'on' ? 'primary' : 'secondary'}
                      onPress={() => toastAfter($, setSwitch($, kind, item.name, flipped(state.switchOf(kind, item.name))))}
                    >
                      {chipLabelOf(state.switchOf(kind, item.name) === 'on', fitLabelOf(item.label, cellChars))}
                    </Button>,
                  ),
                )}
              </Box>
            ))}
          </Box>
        ))
      )}
    </Box>
  )
}

const USAGE = [
  `Usage: /${PLUGIN} <command>`,
  `- <field> <value>: set one value for this session. Fields: ${ALL_FIELDS.join(', ')}`,
  '- agents: list the agent types, each with its switch',
  '- agent <type> on|off: switch one agent type',
  '- skills: list the skills, each with its switch',
  '- skill <name> on|off: switch one skill',
  `- seed <file>: load last-used dates, made by ${BACKFILL_COMMAND}`,
  '- bar: minimize or expand the bar',
  '- apply: move running subagents to the current effort',
  '- save: write this session to the defaults',
  '- reset: drop the values this session set',
  'With no command, it prints the values in force.',
].join('\n')

export const register: Register = (on, options: PluginOptions) => {
  const defaults: Defaults = {
    settings: Object.fromEntries(ALL_FIELDS.map(field => [field, String(options[field])])) as Settings,
    switches: {
      agents: switchesOf(String(options.disabledAgents ?? '')),
      skills: switchesOf(String(options.disabledSkills ?? '')),
    },
  }

  const configuredStaleDays = Number(options.staleDays)
  const staleDays = Number.isInteger(configuredStaleDays) && configuredStaleDays > 0 ? configuredStaleDays : DEFAULT_STALE_DAYS

  on('session.start', async ($, e, next) => {
    await loadLastUsed($)
    await $.command.register({
      name: PLUGIN,
      description: 'Show or change which models, agent types and skills subagents may use, and their effort, for this session',
    })
    $.ui.status(undefined)
    return next(e)
  })

  on('command.run', { command: PLUGIN }, async ($, e) => {
    const [word = '', value, ...rest] = e.args.trim().split(/\s+/).filter(Boolean)
    const state = await sessionState($, defaults)
    if (word === '') return { text: listingOf(state.settings, state.sessionOverrides, state.merged) }
    if (value === undefined) {
      if (word === 'reset') return { text: await resetSession($) }
      if (word === 'save') return { text: await saveDefaults($, defaults) }
      if (word === 'apply') return { text: await applyNow($, defaults) }
      if (word === 'agents') return { text: kindListingOf('agents', state, await read($, offeredAgents)) }
      if (word === 'skills') {
        await refreshSkills($)
        return { text: kindListingOf('skills', state, await read($, knownSkills), await read($, lastUsedDates)) }
      }
      if (word === 'bar') {
        const isOpen = await update($, isBarOpen, current => !current)
        return { text: isOpen ? 'Subagent bar expanded.' : 'Subagent bar minimized.' }
      }
    }
    if (word === 'seed') return { text: rest.length === 0 && value !== undefined ? await seedFrom($, value) : USAGE }
    if (word === 'agent' || word === 'skill') {
      const [nameSwitch, ...extra] = rest
      if (value === undefined || nameSwitch === undefined || !isSwitch(nameSwitch) || extra.length > 0) return { text: USAGE }
      return { text: await setSwitch($, word === 'agent' ? 'agents' : 'skills', value, nameSwitch) }
    }
    if (!isField(word) || value === undefined || rest.length > 0) return { text: USAGE }
    return { text: await setField($, defaults, word, value) }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.surface === 'mobile' || !(await read($, isBarOpen))) return next(e)
    const ui = $.ui.resolve(e)
    const { Box, Text, Button, Select } = ui
    const state = await sessionState($, defaults)
    const { settings } = state
    const allNames = { agents: await panelNamesOf($, defaults, 'agents'), skills: await panelNamesOf($, defaults, 'skills') }
    const inlineData = {
      agents: await panelDataOf($, defaults, 'agents', staleDays),
      skills: await panelDataOf($, defaults, 'skills', staleDays),
    }
    const isPanelOpen = { agents: await isPanelOpenOf($, 'agents'), skills: await isPanelOpenOf($, 'skills') }
    const isSide = { agents: allNames.agents.length > INLINE_LIMIT, skills: allNames.skills.length > INLINE_LIMIT }
    const turnedOffCountOf = (kind: Kind) => allNames[kind].filter(name => state.switchOf(kind, name) === 'off').length
    const runningCount = (await runningAgentIdsOf($)).length
    const optionsOf = (field: keyof Settings) => (ALL_CHOICES[field] as readonly string[]).map(choice => ({ value: choice }))
    const barCell = (key: string, child: unknown) => cellOf(ui, key, BAR_CELL_CHARS, child)
    const gridRowOf = (key: string, cells: unknown[]) => (
      <Box key={key} flexDirection="row" columnGap={BAR_COLUMN_GAP}>
        {cells}
      </Box>
    )

    const panelButtonOf = (kind: Kind) => {
      const mark = isSide[kind] ? (isPanelOpen[kind] ? SIDE_OPEN_MARK : SIDE_CLOSED_MARK) : isPanelOpen[kind] ? MINIMIZE_MARK : EXPAND_MARK
      const count = turnedOffCountOf(kind)
      return (
        <Button key={kind} variant={isPanelOpen[kind] ? 'primary' : 'secondary'} onPress={() => togglePanel($, defaults, kind)}>
          {`${kind} ${count === 0 ? 'all on' : `${count} off`} ${mark}`}
        </Button>
      )
    }

    const selectOf = (field: keyof Settings, label: string, choices?: { value: string; label: string }[]) => (
      <Select
        key={field}
        label={label}
        options={choices ?? optionsOf(field)}
        value={settings[field]}
        onSelect={choice => toastAfter($, setField($, defaults, field, choice))}
      />
    )

    return (
      <Box flexDirection="column" borderStyle="round" borderColor={ACCENT} paddingX={2} gap={1}>
        <Box flexDirection="row" columnGap={COLUMN_GAP} alignItems="center" justifyContent="space-between">
          <Text bold color={ACCENT}>{`${ICON_MARK} Subagents`}</Text>
          <Button key="minimize" dimColor onPress={() => update($, isBarOpen, () => false)}>
            {`${MINIMIZE_MARK} minimize`}
          </Button>
        </Box>
        {gridRowOf(
          'models',
          ALL_FAMILIES.map(family =>
            barCell(
              `model-${family}`,
              <Button
                key={`model-${family}`}
                variant={settings[family] === 'on' ? 'primary' : 'secondary'}
                onPress={() => toastAfter($, setField($, defaults, family, flipped(settings[family])))}
              >
                {chipLabelOf(settings[family] === 'on', family)}
              </Button>,
            ),
          ),
        )}
        {gridRowOf('settings', [
          barCell('cell-defaultModel', selectOf('defaultModel', 'default')),
          barCell('cell-effort', selectOf('effort', 'effort')),
          barCell('cell-offAction', selectOf('offAction', 'if off')),
          barCell(
            'cell-applyToRunning',
            selectOf('applyToRunning', `running ${runningCount}`, [
              { value: 'on', label: 'follow' },
              { value: 'off', label: 'pinned' },
            ]),
          ),
        ])}
        {gridRowOf('actions', [
          barCell('cell-agents', panelButtonOf('agents')),
          barCell('cell-skills', panelButtonOf('skills')),
          barCell(
            'cell-apply',
            <Button key="apply" onPress={() => toastAfter($, applyNow($, defaults))}>
              apply to running
            </Button>,
          ),
          barCell(
            'cell-more',
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
                if (choice === 'reset') void toastAfter($, resetSession($))
              }}
            />,
          ),
        ])}
        {ALL_KINDS.map(kind =>
          isPanelOpen[kind] && !isSide[kind] ? (
            <Box key={`panel-${kind}`} flexDirection="column">
              {panelOf($, ui, inlineData[kind], () => BAR_COLUMNS, true)}
            </Box>
          ) : null,
        )}
      </Box>
    )
  })

  for (const kind of ALL_KINDS) {
    on('ui.render', { component: 'Pane', requestId: PANE_IDS[kind] }, async ($, e) => {
      const data = await panelDataOf($, defaults, kind, staleDays)
      return panelOf($, $.ui.resolve(e), data, cellChars => columnsFor(e.props.bodyColumns, cellChars), false, `${e.props.bodyColumns} columns`)
    })
  }

  on('ui.close', async ($, e, next) => {
    const kind = ALL_KINDS.find(each => PANE_IDS[each] === e.id)
    if (kind !== undefined) await setPanelOpen($, kind, false)
    return next(e)
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
    const { switchOf } = await sessionState($, defaults)
    if (switchOf('agents', e.agent) === 'off') return { isOffered: false }
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    if (e.fork) return next(e)
    const { settings, switchOf } = await sessionState($, defaults)
    if (switchOf('agents', e.subagentType) === 'off') return { deny: `Subagent type ${e.subagentType} is turned off. Pick another subagent_type.` }
    if (e.model === undefined || isAllowed(settings, familyOf(e.model))) return next(e)
    if (settings.offAction === 'deny') return { deny: denyTextOf(e.model, settings) }
    return next({ ...e, model: settings.defaultModel })
  })

  on('skill.prompt', async ($, e, next) => {
    const allSeen = await read($, knownSkills)
    if (!allSeen.includes(e.skill)) await update($, knownSkills, current => [...current, e.skill].sort())
    await recordUse($, e.skill)
    const { merged } = await sessionState($, defaults)
    if (isSkillOff(merged.skills, e.skill)) return { text: skillOffTextOf(e.skill) }
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    if (e.agentId === undefined) return yield* next(e)
    const { settings } = await sessionState($, defaults)
    const model = isAllowed(settings, familyOf(e.model)) ? e.model : settings.defaultModel
    const effort = await effortFor($, settings, e.agentId, e.effort)
    return yield* next({ ...e, model, effort })
  })
}
