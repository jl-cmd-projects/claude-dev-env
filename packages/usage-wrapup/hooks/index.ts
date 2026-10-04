import type { Register } from 'claude-code'
import { register as registerWrapUp } from './register'
import { register as registerCompact } from './compact'

export const register: Register = (on, options) => {
  registerWrapUp(on, options)
  registerCompact(on, options)
}
