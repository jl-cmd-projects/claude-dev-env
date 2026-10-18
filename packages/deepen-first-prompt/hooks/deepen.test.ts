import { test, expect } from 'claude-code/testing'
import { deepenHookInput, deepenHookScriptPath, hasPriorUserMessage, rewrittenPromptFrom } from './deepen'

const GATE_SUFFIX = '/hooks/session/deepen_first_prompt.py'

test('should place the gate under CLAUDE_CONFIG_DIR when it is set', async () => {
  expect(deepenHookScriptPath('/profiles/work', '/home/tester')).toBe(`/profiles/work${GATE_SUFFIX}`)
})

test('should place the gate under the home .claude folder when CLAUDE_CONFIG_DIR is blank', async () => {
  expect(deepenHookScriptPath(undefined, '/home/tester')).toBe(`/home/tester/.claude${GATE_SUFFIX}`)
  expect(deepenHookScriptPath('  ', '/home/tester')).toBe(`/home/tester/.claude${GATE_SUFFIX}`)
})

test('should return no gate path when no root is known', async () => {
  expect(deepenHookScriptPath(undefined, undefined)).toBe(undefined)
  expect(deepenHookScriptPath('', ' ')).toBe(undefined)
})

test('should leave the session id out of the payload when it is missing', async () => {
  expect(JSON.parse(deepenHookInput('Fix the login page', undefined))).toEqual({
    hook_event_name: 'UserPromptSubmit',
    prompt: 'Fix the login page',
  })
  expect(JSON.parse(deepenHookInput('Fix the login page', 'session-7')).session_id).toBe('session-7')
})

test('should take the gate output only when it opens with the marker', async () => {
  expect(rewrittenPromptFrom('  CDE_DEEPEN:v1\n\nDo the expert job.\n')).toBe('CDE_DEEPEN:v1\n\nDo the expert job.')
  expect(rewrittenPromptFrom('')).toBe(undefined)
  expect(rewrittenPromptFrom('{"decision": "skip"}')).toBe(undefined)
  expect(rewrittenPromptFrom('{"decision": "refuse", "reason": "restates-four-questions"}')).toBe(undefined)
})

test('should count only a different user message as a prior turn', async () => {
  const submittedText = 'Add dark mode'
  expect(hasPriorUserMessage([{ role: 'user', text: submittedText }], submittedText)).toBe(false)
  expect(hasPriorUserMessage([{ role: 'assistant', text: 'Hello' }], submittedText)).toBe(false)
  expect(hasPriorUserMessage([{ role: 'user', text: 'Earlier task' }], submittedText)).toBe(true)
})
