import type { Register, SessionRateLimit } from 'claude-code'
import type { CompactedWindows } from '../types'

export const DEFAULT_FIVE_HOUR_PERCENT_USED = 97
export const DEFAULT_SEVEN_DAY_PERCENT_USED = 99

export const COMPACT_INSTRUCTIONS =
  'Usage is near the plan limit. Keep the current task, its exact state, the files it touched, and the next steps.'

const compacted = { plugin: 'usage-wrapup', key: 'compacted' } as const

type Window = { kind: string; resetsAt: string }

/** The first window at or past its percent-used threshold that has not compacted since it last reset. */
export function windowToCompact(
  limits: readonly SessionRateLimit[],
  thresholdByKind: Readonly<Record<string, number>>,
  alreadyCompacted: CompactedWindows,
): Window | undefined {
  for (const limit of limits) {
    const threshold = thresholdByKind[limit.kind]
    if (threshold === undefined || limit.percentUsed < threshold) continue
    const resetsAt = limit.resetsAt ?? ''
    if (alreadyCompacted[limit.kind] !== resetsAt) return { kind: limit.kind, resetsAt }
  }
  return undefined
}

export const register: Register = (on, options) => {
  const thresholdByKind = {
    five_hour: Number(options.compactFiveHour ?? DEFAULT_FIVE_HOUR_PERCENT_USED),
    seven_day: Number(options.compactSevenDay ?? DEFAULT_SEVEN_DAY_PERCENT_USED),
  }

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId !== undefined || e.reason === 'aborted') return done
    try {
      const { rateLimits } = await $.session.usage()
      const { value: alreadyCompacted = {} } = await $.state.get(compacted)
      const window = windowToCompact(rateLimits, thresholdByKind, alreadyCompacted)
      if (window) {
        await $.session.compact({ instructions: COMPACT_INSTRUCTIONS })
        await $.state.set(compacted, { ...alreadyCompacted, [window.kind]: window.resetsAt })
      }
    } catch {
      return done
    }
    return done
  })
}
