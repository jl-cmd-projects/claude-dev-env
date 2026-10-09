# jobs

A small command-line tool that tracks batch jobs.

- `python -m jobs.cli list` prints every job and its status.
- `python -m jobs.cli report --days 7` prints the jobs that finished in the last seven days.
- `python -m jobs.cli cleanup <folder> --days 30` deletes job logs older than thirty days.
- `python -m jobs.cli download <url> <path>` saves a job artifact.

Jobs recieve their status from `jobs.json`.

Run the tests with `python -m pytest tests`.
