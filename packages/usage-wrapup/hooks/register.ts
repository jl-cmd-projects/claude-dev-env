import type { Register, SessionRateLimit } from 'claude-code'
import { isAtOrBelow, readablePercentUsed } from './usage'

const LABEL: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'weekly',
  spend_limit: 'spend',
}

type Low = { kind: string; left: number; resetsAt?: string }

/** The readable window with the least left, when it is at or below the threshold. Windows with no finite reading are skipped. */
export function lowest(limits: readonly SessionRateLimit[], threshold: number): Low | undefined {
  let worst: Low | undefined
  for (const l of limits) {
    const used = readablePercentUsed(l)
    if (used === undefined) continue
    const left = Math.max(0, 100 - used)
    if (!worst || left < worst.left) worst = { kind: l.kind, left, resetsAt: l.resetsAt }
  }
  if (!worst || !isAtOrBelow(worst.left, threshold)) return undefined
  return { ...worst, left: Math.round(worst.left * 10) / 10 }
}

function describe(low: Low): string {
  const name = LABEL[low.kind] ?? low.kind
  const reset = low.resetsAt ? ` It resets at ${low.resetsAt}.` : ''
  return `${name} usage limit: only ${low.left}% left.${reset}`
}

export function wrapUpNote(low: Low): string {
  return [
    `USAGE LOW — ${describe(low)}`,
    'Keep working on the task. Low usage is no reason to end the turn or wait for the reset, unless the user asked you to wait for it.',
    'The limit may cut the session off, so make each step safe to lose:',
    '1. Leave files in a working state after each step, and save finished work the way your task already allows.',
    '2. Keep a short handoff current: what is done, what is left, the exact next step.',
    `3. Arm one wake for just after ${low.resetsAt ?? 'the reset time'}, such as send_later to your own session or a create_trigger routine, so a session the limit cuts off resumes without a person. Skip this step when you already armed that wake.`,
  ].join('\n')
}

export const register: Register = (on, options) => {
  const threshold = Number(options.threshold ?? 1)
  let limits: readonly SessionRateLimit[] | undefined
  let wasWarned = false

  on('session.measure', ($, e, next) => {
    limits = e.rateLimits
    const low = lowest(limits, threshold)
    $.ui.status(low ? `⚠ ${low.left}% left — checkpointing` : undefined)
    if (low && !wasWarned) $.ui.toast(`usage-wrapup: ${describe(low)} Agents told to keep working and checkpoint.`)
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
