import { test, expect } from 'claude-code/testing'
import type { SessionOverrides } from './index'

test('applies a typed session effort override', async ($, on) => {
  on('ui.status', () => ({ value: undefined }) as never)
  const overrides: SessionOverrides = { effort: 'high' }
  const changed = await $.command.run({
    command: 'subagent-models',
    args: `effort ${overrides.effort}`,
    origin: { kind: 'composer' },
    presentation: {},
  } as never)
  const listed = await $.command.run({
    command: 'subagent-models',
    args: '',
    origin: { kind: 'composer' },
    presentation: {},
  } as never)
  expect(changed.text).toBe('effort high for this session.')
  expect(listed.text).toContain('effort high (this session)')
})
