#!/usr/bin/env node
import { createReadStream, existsSync, readdirSync, realpathSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'

const COMMAND_PREFIXES = ['<command-message>', '<command-name>']

const COMMAND_NAME_PATTERN = /<command-name>\/?([^<\s]+)<\/command-name>/

export function skillNameOf(line) {
  if (!line.includes('"name":"Skill"') && !line.includes('<command-name>')) return undefined
  let entry
  try {
    entry = JSON.parse(line)
  } catch {
    return undefined
  }
  const content = entry?.message?.content
  if (entry.type === 'assistant' && Array.isArray(content)) {
    const call = content.find(block => block?.type === 'tool_use' && block.name === 'Skill' && typeof block.input?.skill === 'string')
    return call?.input.skill.replace(/^\//, '')
  }
  if (entry.type === 'user' && !entry.isMeta) {
    const text = typeof content === 'string' ? content : Array.isArray(content) && content[0]?.type === 'text' ? content[0].text : ''
    if (typeof text !== 'string' || !COMMAND_PREFIXES.some(prefix => text.startsWith(prefix))) return undefined
    return COMMAND_NAME_PATTERN.exec(text)?.[1]
  }
  return undefined
}

function* transcriptFilesUnder(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) yield* transcriptFilesUnder(path)
    else if (entry.name.endsWith('.jsonl')) yield path
  }
}

async function scanFile(path, lastUsed) {
  let found = 0
  const lines = createInterface({ input: createReadStream(path, { encoding: 'utf8' }), crlfDelay: Infinity })
  for await (const line of lines) {
    const name = skillNameOf(line)
    if (name === undefined) continue
    const when = Date.parse(JSON.parse(line).timestamp)
    if (Number.isNaN(when)) continue
    found += 1
    if (when > (lastUsed[name] ?? 0)) lastUsed[name] = when
  }
  return found
}

export function defaultRoots(home = homedir()) {
  const candidates = readdirSync(home, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && entry.name.startsWith('.claude'))
    .map(entry => join(home, entry.name))
  const profilesHome = join(home, '.claude-profiles')
  const profiles = existsSync(profilesHome) ? readdirSync(profilesHome).map(name => join(profilesHome, name)) : []
  return [...candidates, ...profiles].filter(root => existsSync(join(root, 'projects')) && statSync(join(root, 'projects')).isDirectory())
}

export async function backfill(roots) {
  const lastUsed = {}
  const perRoot = []
  const scanned = new Set()
  for (const root of roots) {
    const resolved = realpathSync(join(root, 'projects'))
    if (scanned.has(resolved)) {
      perRoot.push({ root, files: 0, uses: 0, aliasOf: resolved })
      continue
    }
    scanned.add(resolved)
    let files = 0
    let uses = 0
    for (const path of transcriptFilesUnder(join(root, 'projects'))) {
      files += 1
      uses += await scanFile(path, lastUsed)
    }
    perRoot.push({ root, files, uses })
  }
  return { generatedAt: new Date().toISOString(), roots: perRoot, lastUsed }
}

function parseArguments(argv) {
  const roots = []
  const excluded = []
  let out
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--root') roots.push(argv[(index += 1)])
    else if (argv[index] === '--exclude') excluded.push(argv[(index += 1)].toLowerCase())
    else if (argv[index] === '--out') out = argv[(index += 1)]
  }
  return { roots, excluded, out }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { roots, excluded, out } = parseArguments(process.argv.slice(2))
  if (out === undefined) {
    console.error('Usage: node backfill-last-used.mjs --out <file.json> [--root <config dir>]... [--exclude <text>]...')
    process.exit(2)
  }
  const chosen = (roots.length > 0 ? roots : defaultRoots()).filter(root => !excluded.some(text => root.toLowerCase().includes(text)))
  const result = await backfill(chosen)
  writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`)
  for (const { root, files, uses, aliasOf } of result.roots) {
    console.log(aliasOf === undefined ? `${root}: ${files} transcripts, ${uses} skill runs` : `${root}: same folder as ${aliasOf}, skipped`)
  }
  console.log(`${Object.keys(result.lastUsed).length} names written to ${out}`)
}
