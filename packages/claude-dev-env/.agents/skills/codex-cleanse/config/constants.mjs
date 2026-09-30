export const DEFAULT_INACTIVE_DAYS = 7;
export const MILLISECONDS_PER_DAY = 86_400_000;
export const MILLISECONDS_PER_SECOND = 1_000;
export const PAGE_SIZE = 1_000;
export const REQUEST_TIMEOUT_MILLISECONDS = 30_000;
export const SOURCE_KINDS = [
    'cli', 'vscode', 'exec', 'appServer', 'subAgent', 'subAgentReview',
    'subAgentCompact', 'subAgentThreadSpawn', 'subAgentOther', 'unknown',
];
export const THREAD_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const ROLLOUT_FILENAME_PATTERN = /^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$/i;
