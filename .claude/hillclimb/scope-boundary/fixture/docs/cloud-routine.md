# Cloud routine

A cloud agent routine runs the reviewer without the desktop runner.

- Fire it with an HTTP POST to the URL in the repository variable `CLOUD_ROUTINE_URL`, with the bearer token in the secret `CLOUD_ROUTINE_TOKEN`.
- The JSON body carries `pull_request`, `model` and `effort`. The routine runs `reviewer exec review` with those values and posts the review comments itself.
- The POST waits until the review finishes, up to 30 minutes. It returns `200` when the review passed and `422` when the reviewer reported blocking findings. Any other status means the routine failed.
- The cloud session holds a reviewer sign-in seeded at setup.
