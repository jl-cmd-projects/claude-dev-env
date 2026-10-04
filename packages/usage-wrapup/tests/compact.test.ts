import { test, expect } from 'claude-code/testing'
import type { On, SessionRateLimit } from 'claude-code'

type Engine = { compactions: (string | undefined)[]; setLimits: (limits: SessionRateLimit[]) => void }

function engine(on: On, initial: SessionRateLimit[]): Engine {
  let rateLimits = initial
  const compactions: (string | undefined)[] = []
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 200000 }, rateLimits } }) as never)
  on('session.compact', (_$, e) => (compactions.push(e.instructions), { messages: [{ role: 'user', text: 'summary', toolUses: [] }] }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  on('ui.status', () => ({}) as never)
  on('ui.toast', () => ({}) as never)
  return { compactions, setLimits: (limits) => (rateLimits = limits) }
}

const fiveHour = (percentUsed: number, resetsAt = '2026-10-02T20:00:00Z'): SessionRateLimit => ({
  kind: 'five_hour',
  percentUsed,
  resetsAt,
})

const sevenDay = (percentUsed: number): SessionRateLimit => ({
  kind: 'seven_day',
  percentUsed,
  resetsAt: '2026-10-08T00:00:00Z',
})

const endTurn = { reason: 'answer', answer: 'done', durationMs: 1, isAborted: false, turnId: 't1' } as const

test('compacts when the five-hour window reaches 97% used', async ($, on) => {
  const world = engine(on, [fiveHour(97.0)])
  await $.turn.complete(endTurn)
  expect(world.compactions).toHaveLength(1)
  expect(world.compactions[0]).toMatch(/Keep the current task/)
})

test('does not compact at 96.9% of the five-hour window', async ($, on) => {
  const world = engine(on, [fiveHour(96.9)])
  await $.turn.complete(endTurn)
  expect(world.compactions).toHaveLength(0)
})

test('compacts when the seven-day window reaches 99% used', async ($, on) => {
  const world = engine(on, [fiveHour(10), sevenDay(99)])
  await $.turn.complete(endTurn)
  expect(world.compactions).toHaveLength(1)
})

test('does not compact at 98.9% of the seven-day window', async ($, on) => {
  const world = engine(on, [sevenDay(98.9)])
  await $.turn.complete(endTurn)
  expect(world.compactions).toHaveLength(0)
})

test('compacts once per window', async ($, on) => {
  const world = engine(on, [fiveHour(98)])
  await $.turn.complete(endTurn)
  await $.turn.complete({ ...endTurn, turnId: 't2' })
  expect(world.compactions).toHaveLength(1)
})

test('compacts again after the window resets', async ($, on) => {
  const world = engine(on, [fiveHour(98)])
  await $.turn.complete(endTurn)
  world.setLimits([fiveHour(98, '2026-10-03T01:00:00Z')])
  await $.turn.complete({ ...endTurn, turnId: 't2' })
  expect(world.compactions).toHaveLength(2)
})

test('leaves an interrupted turn alone', async ($, on) => {
  const world = engine(on, [fiveHour(99)])
  await $.turn.complete({ ...endTurn, reason: 'aborted', isAborted: true })
  expect(world.compactions).toHaveLength(0)
})

test('leaves a subagent turn alone', async ($, on) => {
  const world = engine(on, [fiveHour(99)])
  await $.turn.complete({ ...endTurn, agentId: 'a1' })
  expect(world.compactions).toHaveLength(0)
})

test('options override the default thresholds', { options: { compactFiveHour: 50, compactSevenDay: 60 } }, async ($, on) => {
  const world = engine(on, [fiveHour(50)])
  await $.turn.complete(endTurn)
  world.setLimits([fiveHour(10), sevenDay(60)])
  await $.turn.complete({ ...endTurn, turnId: 't2' })
  expect(world.compactions).toHaveLength(2)
})

test('the default five-hour threshold holds below 97% when options are unset', async ($, on) => {
  const world = engine(on, [fiveHour(50)])
  await $.turn.complete(endTurn)
  expect(world.compactions).toHaveLength(0)
})
