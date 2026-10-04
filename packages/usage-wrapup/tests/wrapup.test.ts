import { test, expect } from 'claude-code/testing'
import type { On } from 'claude-code'

const toasts: string[] = []

function engine(on: On, usedPercent?: number) {
  const rateLimits = usedPercent === undefined ? [] : [{ kind: 'five_hour', percentUsed: usedPercent }]
  on('session.measure', (_$, e) => ({ changed: e.changed }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 200000 }, rateLimits } }) as never)
  on('ui.toast', (_$, e) => (toasts.push(String((e as { text?: unknown }).text ?? e)), {}) as never)
  on('ui.status', () => ({}) as never)
  on('tool.call', () => ({ result: 'ok', text: 'ok' }) as never)
}

const measure = (percentUsed: number) => ({
  context: { window: 200000 },
  rateLimits: [{ kind: 'five_hour', percentUsed }],
  changed: ['rateLimits' as const],
})

test('no note while plenty of usage is left', async ($, on) => {
  engine(on)
  await $.session.measure(measure(50))
  const r = await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  expect((r as { context?: string[] }).context ?? []).toHaveLength(0)
})

test('tool results carry the wrap-up note at 5% left or less', async ($, on) => {
  engine(on)
  await $.session.measure(measure(96))
  const r = await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  const ctx = (r as { context?: string[] }).context ?? []
  expect(ctx.join('\n')).toMatch(/USAGE LOW .*4% left/)
  expect(ctx.join('\n')).toMatch(/handoff/)
})

test('reads usage itself when no measurement came yet', async ($, on) => {
  engine(on, 99)
  const r = await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  expect(((r as { context?: string[] }).context ?? []).join('\n')).toMatch(/1% left/)
})

test('threshold is configurable', { options: { threshold: 20 } }, async ($, on) => {
  engine(on)
  await $.session.measure(measure(85))
  const r = await $.tool.call({ tool: 'Bash', command: 'ls' } as never)
  expect(((r as { context?: string[] }).context ?? []).join('\n')).toMatch(/15% left/)
})
