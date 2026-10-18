export const DEEPEN_MARKER = 'CDE_DEEPEN:v1'
export const DEEPEN_OUTPUT_MODE = 'rewrite'
export const HOOK_TIMEOUT_MILLISECONDS = 8000
export const ALL_PYTHON_LAUNCHERS: readonly (readonly string[])[] = [['python3'], ['python']]

type SessionMessage = { role?: unknown; text?: unknown }

/** The managed gate under CLAUDE_CONFIG_DIR, or under ~/.claude when that variable is unset. */
export function deepenHookScriptPath(
  configDirectory: string | undefined,
  homeDirectory: string | undefined,
): string | undefined {
  const configRoot = configDirectory?.trim()
  const homeRoot = homeDirectory?.trim()
  const claudeRoot = configRoot || (homeRoot ? `${homeRoot}/.claude` : undefined)
  return claudeRoot === undefined ? undefined : `${claudeRoot}/hooks/session/deepen_first_prompt.py`
}

/** The UserPromptSubmit payload the Python gate reads. A missing session id is left out. */
export function deepenHookInput(prompt: string, sessionId: string | undefined): string {
  return JSON.stringify({
    hook_event_name: 'UserPromptSubmit',
    prompt,
    ...(sessionId ? { session_id: sessionId } : {}),
  })
}

/** The rewritten task when the gate printed one that opens with the marker. */
export function rewrittenPromptFrom(stdout: string): string | undefined {
  const printed = stdout.trim()
  return printed.startsWith(DEEPEN_MARKER) ? printed : undefined
}

/** True when the session already holds a user message other than the one being submitted. */
export function hasPriorUserMessage(allMessages: readonly SessionMessage[], submittedText: string): boolean {
  return allMessages.some(eachMessage => eachMessage.role === 'user' && eachMessage.text !== submittedText)
}
