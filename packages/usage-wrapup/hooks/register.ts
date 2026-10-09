import type { Register, SessionRateLimit } from 'claude-code'

const LABEL: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'weekly',
  spend_limit: 'spend',
}

type Low = { kind: string; left: number; resetsAt?: string }

/** The window with the least left, when it is at or below the threshold. */
export function lowest(limits: readonly SessionRateLimit[], threshold: number): Low | undefined {
  let worst: Low | undefined
  for (const l of limits) {
    const left = Math.max(0, Math.round((100 - l.percentUsed) * 10) / 10)
    if (!worst || left < worst.left) worst = { kind: l.kind, left, resetsAt: l.resetsAt }
  }
  return worst && worst.left <= threshold ? worst : undefined
}

function describe(low: Low): string {
  const name = LABEL[low.kind] ?? low.kind
  const reset = low.resetsAt ? ` It resets at ${low.resetsAt}.` : ''
  return `${name} usage limit: only ${low.left}% left.${reset}`
}

export function wrapUpNote(low: Low): string {
  return [
    `USAGE LOW — ${describe(low)}`,
    'You may be cut off soon. Wrap up now:',
    '1. Do not start new work, new subagents or big searches.',
    '2. Finish or safely pause the current step. Leave files in a working state.',
    '3. Write a short handoff: what is done, what is left, the exact next step.',
    `4. Before you stop, arm one wake for just after ${low.resetsAt ?? 'the reset time'}, such as send_later to your own session or a create_trigger routine, so the paused work resumes without a person.`,
    '5. Then stop and give the user your final answer.',
  ].join('\n')
}

export const register: Register = (on, options) => {
  const threshold = Number(options.threshold ?? 1)
  let limits: readonly SessionRateLimit[] | undefined
  let wasWarned = false

  on('session.measure', ($, e, next) => {
    limits = e.rateLimits
    const low = lowest(limits, threshold)
    $.ui.status(low ? `⚠ ${low.left}% left — wrapping up` : undefined)
    if (low && !wasWarned) $.ui.toast(`usage-wrapup: ${describe(low)} Agents told to wrap up.`)
    wasWarned = !!low
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if ('deny' in ran && ran.deny !== undefined) return ran
    if (!limits) {
      try {
        limits = (await $.session.usage()).rateLimits
      } catch {
        limits = []
      }
    }
    const low = lowest(limits, threshold)
    if (!low) return ran
    return { ...ran, context: [...(ran.context ?? []), wrapUpNote(low)] }
  })
}
