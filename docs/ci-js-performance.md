# Compare JS test performance

Run the full `npm test` command from `packages/claude-dev-env` on the baseline
and candidate revisions. Use separate checkouts, the same operating system,
Node 24, and the dependencies installed by `.github/workflows/ci-tests.yml`.
Capture each command's combined output in a UTF-8 file outside its checkout.
Keep the default Node spec reporter and disable terminal colors.

From the candidate repository root, compare the two reports:

```sh
python .github/ci/compare_js_test_runs.py before.log after.log
```

The comparison requires matching test counts and passed-test names, no failed
or cancelled tests, and a duration at most half the baseline. Use `--max-ratio`
to set another duration limit. Identical reports pass with `--max-ratio 1` and
fail with the default limit. A report with a missing passed-test line fails.

The package command caps parallel execution at four test files. Each file's
tests remain sequential. The Windows npm test step sets `TEMP` and `TMP` to
`runner.temp`, placing scratch homes on the runner's work volume.
The previous cap of one followed a lifecycle timeout
under parallel load in [PR 1828](https://github.com/jl-cmd-projects/claude-dev-env/pull/1828).
Measure on both Ubuntu and Windows before raising the cap again.
