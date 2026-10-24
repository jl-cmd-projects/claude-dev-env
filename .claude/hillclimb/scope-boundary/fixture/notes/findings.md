# Findings from the cloud trials (yesterday)

1. Two reviews started at the same moment both finished with exit 0 on one shared reviewer sign-in.
2. The reviewer sign-in has to refresh about every 10 days. If two sessions refresh at the same moment, one of them can be signed out.
3. The cloud session's network proxy refuses writes to the GitHub check-runs API.
4. The review App's private key has only ever been used from the desktop runner.
5. Branch protection requires the `ai-review` check to pass before merge.
