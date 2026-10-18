import type { Register } from 'claude-code'
import {
  ALL_PYTHON_LAUNCHERS,
  DEEPEN_OUTPUT_MODE,
  HOOK_TIMEOUT_MILLISECONDS,
  deepenHookInput,
  deepenHookScriptPath,
  hasPriorUserMessage,
  rewrittenPromptFrom,
} from './deepen'

export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    const allMessages = await $.session.messages().catch(() => [])
    if (hasPriorUserMessage(allMessages, e.text)) return next(e)
    const homeDirectory = (await $.env.get('HOME')) ?? (await $.env.get('USERPROFILE'))
    const scriptPath = deepenHookScriptPath(await $.env.get('CLAUDE_CONFIG_DIR'), homeDirectory)
    if (scriptPath === undefined) return next(e)
    const sessionId = await $.session.id().catch(() => undefined)
    const stdin = deepenHookInput(e.text, sessionId)
    for (const eachLauncher of ALL_PYTHON_LAUNCHERS) {
      const gateRun = await $.process
        .run([...eachLauncher, scriptPath], {
          env: { CDE_DEEPEN_OUTPUT: DEEPEN_OUTPUT_MODE },
          stdin,
          timeoutMs: HOOK_TIMEOUT_MILLISECONDS,
        })
        .catch(() => undefined)
      if (gateRun === undefined || gateRun.exitCode !== 0) continue
      const rewritten = rewrittenPromptFrom(gateRun.stdout)
      return next(rewritten === undefined ? e : { ...e, text: rewritten })
    }
    return next(e)
  })
}
