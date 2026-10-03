import { test, expect } from 'claude-code/testing'

test('registers the model settings command', async $ => {
  const answer = await $.command.run({
    command: 'subagent-models',
    args: '',
    origin: { kind: 'composer' },
    presentation: {},
  } as never)
  expect(answer.text).toContain('defaultModel opus')
  expect(answer.text).toContain('effort medium')
})
