import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, test } from 'node:test'

import { backfill, defaultRoots, skillNameOf } from './backfill-last-used.mjs'

const workDirectory = mkdtempSync(join(tmpdir(), 'backfill-last-used-'))

after(() => rmSync(workDirectory, { recursive: true, force: true }))

const skillCall = (skill, timestamp) =>
  JSON.stringify({ type: 'assistant', timestamp, message: { content: [{ type: 'tool_use', name: 'Skill', input: { skill } }] } })

const typedCommand = (name, timestamp) =>
  JSON.stringify({ type: 'user', timestamp, message: { content: `<command-message>${name}</command-message>\n<command-name>/${name}</command-name>` } })

const quotedCommand = timestamp =>
  JSON.stringify({ type: 'assistant', timestamp, message: { content: [{ type: 'text', text: 'see <command-name>/ghost</command-name> in the log' }] } })

const pastedCommand = timestamp =>
  JSON.stringify({ type: 'user', timestamp, message: { content: 'look at this log: <command-name>/ghost</command-name> ran' } })

function makeRoot(name, files) {
  const root = join(workDirectory, name)
  const project = join(root, 'projects', 'project-a', 'session-1', 'subagents')
  mkdirSync(project, { recursive: true })
  Object.entries(files).forEach(([file, lines]) => writeFileSync(join(project, file), `${lines.join('\n')}\n`))
  return root
}

test('a Skill tool call and a typed slash command both name a skill', () => {
  assert.equal(skillNameOf(skillCall('pstack:tdd', '2026-10-01T00:00:00Z')), 'pstack:tdd')
  assert.equal(skillNameOf(typedCommand('simplify', '2026-10-01T00:00:00Z')), 'simplify')
})

test('a command tag quoted inside assistant or user text names nothing', () => {
  assert.equal(skillNameOf(quotedCommand('2026-10-01T00:00:00Z')), undefined)
  assert.equal(skillNameOf(pastedCommand('2026-10-01T00:00:00Z')), undefined)
})

test('the newest run across roots and files wins, and each root reports its own count', async () => {
  const first = makeRoot('first', {
    'a.jsonl': [skillCall('tdd', '2026-09-01T00:00:00Z'), typedCommand('simplify', '2026-09-20T00:00:00Z'), quotedCommand('2026-09-30T00:00:00Z'), pastedCommand('2026-09-30T00:00:00Z')],
  })
  const second = makeRoot('second', { 'b.jsonl': [skillCall('tdd', '2026-09-25T00:00:00Z'), 'not json at all <command-name>'] })
  const result = await backfill([first, second])
  assert.equal(result.lastUsed.tdd, Date.parse('2026-09-25T00:00:00Z'))
  assert.equal(result.lastUsed.simplify, Date.parse('2026-09-20T00:00:00Z'))
  assert.equal(result.lastUsed.ghost, undefined)
  assert.deepEqual(result.roots.map(({ files, uses }) => [files, uses]), [[1, 2], [1, 1]])
})

test('default roots take every dot-claude directory and profile that holds transcripts', () => {
  const home = join(workDirectory, 'home')
  mkdirSync(join(home, '.claude', 'projects'), { recursive: true })
  mkdirSync(join(home, '.claude-raw', 'projects'), { recursive: true })
  mkdirSync(join(home, '.claude-empty'), { recursive: true })
  mkdirSync(join(home, '.claude-profiles', 'org', 'projects'), { recursive: true })
  mkdirSync(join(home, '.claude-profiles', 'bare'), { recursive: true })
  const roots = defaultRoots(home).map(root => root.slice(home.length + 1).replaceAll('\\', '/')).sort()
  assert.deepEqual(roots, ['.claude', '.claude-profiles/org', '.claude-raw'])
})

test('a root whose transcripts folder is a link to another root is scanned once', async () => {
  const original = makeRoot('original', { 'a.jsonl': [skillCall('tdd', '2026-09-01T00:00:00Z')] })
  const alias = join(workDirectory, 'alias')
  mkdirSync(alias, { recursive: true })
  symlinkSync(join(original, 'projects'), join(alias, 'projects'), 'junction')
  const result = await backfill([original, alias])
  assert.deepEqual(result.roots.map(({ files, uses }) => [files, uses]), [[1, 1], [0, 0]])
  assert.equal(result.roots[1].aliasOf, realpathSync(join(original, 'projects')))
})
