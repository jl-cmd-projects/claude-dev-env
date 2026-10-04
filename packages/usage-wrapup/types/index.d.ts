export type CompactedWindows = Record<string, string>

declare module 'claude-code' {
  interface PluginState {
    'usage-wrapup': { compacted: CompactedWindows }
  }
}
