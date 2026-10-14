import type { Register, SessionRateLimit } from 'claude-code'
import { isAtOrBelow, readablePercentUsed } from './usage'

const LABEL: Record<string, string> = {
  five_hour: '5-hour',
  seven_day: 'weekly',
  spend_limit: 'spend',
}

type Low = { kind: string; left: number; resetsAt?: string }

type UsageRead =
  | { kind: 'pending'; limits: Promise<readonly SessionRateLimit[] | undefined> }
  | { kind: 'failed'; at: number }

const USAGE_RETRY_MILLISECONDS = 60_000

function isCoolingDown(read: UsageRead | undefined, now: number): boolean {
  if (read?.kind !== 'failed') return false
  const sinceFailure = now - read.at
  return sinceFailure >= 0 && sinceFailure < USAGE_RETRY_MILLISECONDS
}

async function readUsageLimits(
  readUsage: () => Promise<{ rateLimits?: readonly SessionRateLimit[] }>,
): Promise<readonly SessionRateLimit[] | undefined> {
  try {
    return (await readUsage())?.rateLimits
  } catch {
    return undefined
  }
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
  let usageRead: UsageRead | undefined

  const startUsageRead = (readUsage: () => Promise<{ rateLimits?: readonly SessionRateLimit[] }>) => {
    const pending = readUsageLimits(readUsage)
    usageRead = { kind: 'pending', limits: pending }
    void pending.then((read) => {
      usageRead = read ? undefined : { kind: 'failed', at: Date.now() }
    })
    return pending
  }

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
      if (isCoolingDown(usageRead, Date.now())) return ran
      const pending = usageRead?.kind === 'pending' ? usageRead.limits : startUsageRead(() => $.session.usage())
      const read = await pending
      limits ??= read
      if (!limits) return ran
    }
    const low = lowest(limits, threshold)
    if (!low) return ran
    return { ...ran, context: [...(ran.context ?? []), wrapUpNote(low)] }
  })
}
