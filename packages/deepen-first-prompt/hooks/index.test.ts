import { test, expect } from 'claude-code/testing'
import type { On } from 'claude-code'

type RunRequest = { argv: string[]; init?: { env?: Record<string, string>; stdin?: string; timeoutMs?: number } }
type RunAnswer = { exitCode: number; stdout: string; stderr: string } | Error

const FIRST_TASK = 'Add dark mode to the settings page'
const REWRITTEN_TASK = 'CDE_DEEPEN:v1\n\nShip contrast tokens with the theme and prove it with a screenshot.'

function engine(on: On, answerFor: (request: RunRequest) => RunAnswer, allMessages: unknown[] = []) {
  const allRequests: RunRequest[] = []
  const allSubmittedTexts: string[] = []
  on('session.messages', () => allMessages as never)
  on('session.id', () => 'session-deepen' as never)
  on('env.get', (_$, e) => ((e as { name: string }).name === 'HOME' ? '/home/tester' : undefined) as never)
  on('process.run', (_$, e) => {
    const request = e as unknown as RunRequest
    allRequests.push(request)
    const answer = answerFor(request)
    if (answer instanceof Error) throw answer
    return answer as never
  })
  on('prompt.submit', (_$, e) => {
    allSubmittedTexts.push(e.text)
    return {} as never
  })
  return { allRequests, allSubmittedTexts }
}

test('should replace the submitted text when the gate prints a rewrite', async ($, on) => {
  const world = engine(on, () => ({ exitCode: 0, stdout: `${REWRITTEN_TASK}\n`, stderr: '' }))
  await $.prompt.submit({ text: FIRST_TASK })
  expect(world.allSubmittedTexts).toEqual([REWRITTEN_TASK])
  expect(world.allRequests[0]?.argv).toEqual(['python3', '/home/tester/.claude/hooks/session/deepen_first_prompt.py'])
  expect(world.allRequests[0]?.init?.env).toEqual({ CDE_DEEPEN_OUTPUT: 'rewrite' })
  expect(world.allRequests[0]?.init?.timeoutMs).toBe(8000)
  expect(JSON.parse(world.allRequests[0]?.init?.stdin ?? '{}')).toEqual({
    hook_event_name: 'UserPromptSubmit',
    prompt: FIRST_TASK,
    session_id: 'session-deepen',
  })
})

test('should leave the submitted text when the gate skips', async ($, on) => {
  const world = engine(on, () => ({ exitCode: 0, stdout: '', stderr: '' }))
  await $.prompt.submit({ text: 'thanks' })
  expect(world.allSubmittedTexts).toEqual(['thanks'])
  expect(world.allRequests).toHaveLength(1)
})

test('should leave the submitted text when no python launcher starts', async ($, on) => {
  const world = engine(on, () => new Error('failed to start: ENOENT'))
  await $.prompt.submit({ text: FIRST_TASK })
  expect(world.allSubmittedTexts).toEqual([FIRST_TASK])
  expect(world.allRequests.map(eachRequest => eachRequest.argv[0])).toEqual(['python3', 'python'])
})

test('should try python when python3 exits non-zero', async ($, on) => {
  const world = engine(on, request =>
    request.argv[0] === 'python3'
      ? { exitCode: 9009, stdout: '', stderr: 'Python was not found' }
      : { exitCode: 0, stdout: REWRITTEN_TASK, stderr: '' },
  )
  await $.prompt.submit({ text: FIRST_TASK })
  expect(world.allSubmittedTexts).toEqual([REWRITTEN_TASK])
})

test('should leave a later turn without running the gate', async ($, on) => {
  const world = engine(
    on,
    () => ({ exitCode: 0, stdout: REWRITTEN_TASK, stderr: '' }),
    [{ role: 'user', text: FIRST_TASK, toolUses: [] }],
  )
  await $.prompt.submit({ text: 'and the billing page too' })
  expect(world.allSubmittedTexts).toEqual(['and the billing page too'])
  expect(world.allRequests).toHaveLength(0)
})
