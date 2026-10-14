import type { SessionRateLimit } from 'claude-code'

const THRESHOLD_TOLERANCE = 1e-9

/** The window's percent used, or undefined when the host sent no finite reading. */
export function readablePercentUsed(limit: SessionRateLimit): number | undefined {
  return Number.isFinite(limit.percentUsed) ? limit.percentUsed : undefined
}

/** Whether value is at or below bound within float error; false when either is NaN. */
export function isAtOrBelow(value: number, bound: number): boolean {
  return value <= bound + THRESHOLD_TOLERANCE
}

/** Whether value has reached bound within float error; false when either is NaN. */
export function isAtOrPast(value: number, bound: number): boolean {
  return isAtOrBelow(bound, value)
}
