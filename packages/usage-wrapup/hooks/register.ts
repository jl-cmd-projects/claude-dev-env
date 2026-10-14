import type { Register, SessionRateLimit } from 'claude-code'

const LABEL: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'weekly',
  spend_limit: 'spend',
}

type Low = { kind: string; left: number; resetsAt?: string }

const THRESHOLD_TOLERANCE = 1e-9
const USAGE_RETRY_MILLISECONDS = 60_000

/** The window's percent used, or undefined when the host sent no finite reading. */
export function readablePercentUsed(limit: SessionRateLimit): number | undefined {
  return Number.isFinite(limit.percentUsed) ? limit.percentUsed : undefined
}

function isAtOrBelow(left: number, threshold: number): boolean {
  return left <= threshold + THRESHOLD_TOLERANCE
}

function isCoolingDown(failedAt: number | undefined, now: number): boolean {
  if (failedAt === undefined) return false
  const sinceFailure = now - failedAt
  return sinceFailure >= 0 && sinceFailure < USAGE_RETRY_MILLISECONDS
}

/** The window with the least left, when it is at or below the threshold. */
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
  let usageReadFailedAt: number | undefined
  let usageRead: Promise<readonly SessionRateLimit[] | undefined> | undefined

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
      if (isCoolingDown(usageReadFailedAt, Date.now())) return ran
      usageRead ??= $.session
        .usage()
        .then(
          (usage) => usage.rateLimits,
          () => {
            usageReadFailedAt = Date.now()
            return undefined
          },
        )
        .finally(() => {
          usageRead = undefined
        })
      limits = await usageRead
      if (!limits) return ran
    }
    const low = lowest(limits, threshold)
    if (!low) return ran
    return { ...ran, context: [...(ran.context ?? []), wrapUpNote(low)] }
  })
}
