# Repository `.claude/hooks`

This repository's own `.claude/settings.json` registers one SessionStart hook for sessions opened on this checkout. At a cloud session start, `.claude/hooks/session_start_refresh.py` compares the installed `claude-dev-env` version with the npm registry version. When they differ, it runs `npx -y claude-dev-env@<registry version>`. Once the module loads, the hook exits `0` on every path, because `main` runs inside a `try` that turns any `Exception` into the `HOOK_ERROR` message. It prints nothing only when the install is known to be current: the manifest already matches the registry, or the install exits `0` and the manifest then matches. Every other remote start prints one JSON `systemMessage` line. The `config` import and the `re.compile` of the registry version pattern run at module load, before that `try` and before the remote guard. A `config/` that does not import, or a pattern that does not compile, prints a traceback on stderr and exits `1` in every session. [The cloud session guide](../../../../docs/claude-code-on-the-web.md) states why the hook exists. The package hooks have their own map in [Hook lifecycle](hook-lifecycle.md).

## Sub-features

- `registration`. The SessionStart group with matcher `startup|resume` runs `node .claude/hooks/python_script_launcher.js .claude/hooks/session_start_refresh.py` with timeout `630`.
- `launcher`. `python_script_launcher.js` starts `python3`, then `python` (`py -3`, then `python`, on Windows), passes the script's stdout and stderr through, and returns the script's exit code. It exits `1` with no Python on `PATH`, when Python fails to start, or when the script ends on a signal. It exits `2` with no script argument, which the registration always passes.
- `local-guard`. A `CLAUDE_CODE_REMOTE` value other than `true` exits before any tool call.
- `current-install`. A manifest version equal to the registry version costs one `npm view claude-dev-env version` call and runs no install.
- `stale-install`. A manifest version that differs from the registry version runs `npx -y claude-dev-env@<registry version>`. The hook compares the two with `==`, so a newer manifest version also installs the older registry version. A missing manifest installs too, and so does one that is not JSON, not an object, or has no string `version`. Both calls run from the home directory.
- `config-dir`. `CLAUDE_CONFIG_DIR` moves the manifest the hook reads. A relative or `~` value anchors to the home directory. The install gets the resolved absolute path in `CLAUDE_CONFIG_DIR`.
- `fail-open`. Every case below exits `0`. No `npm`, a non-zero `npm` exit, a registry answer that is not a bare version, and a probe past 30 seconds run no install and print the lookup message, `claude-dev-env refresh: `npm view claude-dev-env version` gave no version, ...`, which names `npx -y claude-dev-env@latest`.
- `refresh-outcomes`. `RefreshOutcome` in `.claude/hooks/config/session_start_refresh_constants.py` is the closed set of outcomes that leave the install not known to be current, and each member's value is its message. Every message starts `claude-dev-env refresh: ` and names a command to run by hand. No `npx` prints `<version> did not install, because npx was not found on PATH or could not start`. An install past 570 seconds kills the tool's process group and prints `the install of <version> ran past 570 seconds and was stopped before it ended, and the manifest shows <installed>`. An install that ends on a signal prints `the install of <version> was stopped by signal <n> before it ended, and the manifest shows <installed>`. Neither message says which files the stopped install changed. An install that exits `0` while the manifest still shows another version prints `exited 0, but the manifest shows <old> instead of <version>`. An exception inside `main` prints `the refresh hook stopped on <error type>`. These cases write no failed record, so the next start runs the install again.
- `unfinished-refresh`. Before the install starts, the hook writes its own in-progress record beside the manifest, `.claude-dev-env-refresh-in-progress.<pid>`, which holds `{"version": "<version>", "pid": <pid>, "started_at": <epoch seconds>}`. It removes that file when the install call returns. A hook killed from outside leaves its record. The install itself runs in its own session, so it can outlive the hook. A later start reads every file whose name starts `.claude-dev-env-refresh-in-progress`. A record whose process still runs and whose `started_at` is less than 630 seconds old belongs to a live run, and the start leaves it alone. Every other record is a stopped run, and the start removes it. A file that holds only a version, such as the driver's `--in-progress-record` seed, is a stopped run too. For each stopped run, the message gains the line `claude-dev-env refresh: the refresh hook was stopped at an earlier session start before its install of <version> ended, ...`, unless the manifest at the end of this start shows that version or a later one. On Windows the hook does not test the process, so every record reads as stopped there.
- `failed-install`. An install that exits with a code above `0` prints one JSON line on stdout, `{"systemMessage": "claude-dev-env refresh: `npx -y claude-dev-env@<version>` failed with exit code <n>, ..."}`, and writes `<version>` to `.claude-dev-env-refresh-failed-version` beside the manifest. Claude Code shows a SessionStart `systemMessage` to the user. A later start whose registry version matches the record skips the install and prints a `systemMessage` that starts `claude-dev-env refresh: skipped <version>` and names the retry command. A registry version that differs from the record installs as usual.

## How to get to it (user POV)

- Open a Claude Code session on this repository on the web, where `CLAUDE_CODE_REMOTE=true` is set. A `startup` or `resume` start runs the hook. A `clear` or `compact` start does not.
- Change a file under `.claude/hooks/`, or the SessionStart entry in `.claude/settings.json`. The next session start runs the changed code.

## Driving it with the scratch driver

The skill's Launch and Doctor commands never run this repository's `.claude/hooks/`. `verify-installer.mjs run` installs `packages/claude-dev-env` into a disposable home, and `doctor` checks the tools that run needs, so a change limited to this hook needs only this drive. Keep this feature's proof in `<evidence>`, outside the checkout. The evidence folder that `SKILL.md` names sits inside the checkout and holds the installer transcript.

Preconditions:

- A Linux shell has `bash`, `node`, `python3`, `sleep`, `timeout`, `sha256sum`, and `git` on `PATH`.
- `<repository>` is the absolute path of a git work tree that holds the `.claude/settings.json` and `.claude/hooks/` to drive. The seed's `repository=` line sets it, and the drive runs the hook from that folder. For the hook as it stands in this checkout, edited or not, it is this checkout. To drive a changed copy of the hook folder kept elsewhere, put the copy in a git work tree outside the checkout, such as a `git clone` of this checkout with the change applied, and name that work tree on `repository=`.
- `<scratch>` is a new absolute path under the OS temporary root, such as `/tmp/claude-hooks-verify-<run id>`. The seed block refuses a path that exists.
- `<evidence>` is an absolute path outside `<scratch>` and outside the repository, such as a folder in the session scratchpad.

**Isolation rule.** Run the hook only through `<scratch>/drive`. Never run the registered command, `session_start_refresh.py`, or `python_script_launcher.js` with the session's own environment. A cloud session sets `CLAUDE_CODE_REMOTE=true`, so that run asks the registry for a version and can run the published installer over the live `~/.claude` tree. The driver builds the hook's environment from empty with `env -i`. `HOME` and `USERPROFILE` are a new folder under `<scratch>/homes/`. `PATH` is one `<scratch>/bin*` folder that holds links to `node`, `python3`, and `sleep`, plus `npm` and `npx` stubs that only append a line to a log. `PYTHONDONTWRITEBYTECODE=1` keeps `__pycache__` out of `.claude/hooks`. Before each drive, the driver runs a doctor under the same environment. The doctor stops the drive with exit `3` when the home, the configuration folder the hook resolves, or a tool on `PATH` is outside `<scratch>`. The doctor imports `session_start_refresh` before the hook runs, so a module that does not load also stops the drive with exit `3`, after the traceback. Each drive reads `git status --porcelain --untracked-files=all --ignored` before the doctor. A drive that runs the hook reads it again after the hook, so a new file under an ignored `__pycache__` counts as a change, and hashes the live manifest just before and after the hook. When that first `git status` fails, the drive prints `drive: git status failed in <repository>, hook not run` and exits `5`.

Seed the scratch folder once. Save the block to a file outside the repository, such as `<evidence>-seed.sh`, with a file write tool, or with `sed -n '<first>,<last>p'` on this file, where `<first>` and `<last>` are the block's first and last lines inside the fence. Some sessions have a Bash gate that refuses an `awk` or heredoc extraction. Set the three paths on its first three lines, then run `bash <evidence>-seed.sh`. When the hook folder does not import, the seed prints `seed: cannot resolve the live manifest path from <repository>/.claude/hooks`, exits `1`, and makes no `<scratch>`:

```bash
scratch=/tmp/claude-hooks-verify-run1
evidence=/abs/path/to/evidence
repository=/abs/path/to/claude-dev-env
live_manifest_path=$(python3 -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import session_start_refresh as hook; print(hook.claude_config_directory() / hook.MANIFEST_FILE_NAME)' "$repository/.claude/hooks") && [ -n "$live_manifest_path" ] || { echo "seed: cannot resolve the live manifest path from $repository/.claude/hooks"; exit 1; }
mkdir "$scratch" || exit 1
mkdir -p "$evidence" "$scratch/homes"
cd "$scratch" || exit 1
printf '%s\n' "$repository" > repository-root
printf '%s\n' "$evidence" > evidence-root
printf '%s\n' "$live_manifest_path" > live-manifest-path
command -v python3 > doctor-python
cat > npm-stub <<'STUB'
#!/bin/bash
printf 'npm %s cwd=%s pid=%s\n' "$*" "$PWD" "$$" >> "$STUB_LOG"
if [ -n "${STUB_NPM_SLEEP:-}" ]; then exec sleep "$STUB_NPM_SLEEP"; fi
if [ -n "${STUB_NPM_EXIT:-}" ]; then exit "$STUB_NPM_EXIT"; fi
printf '%s\n' "${STUB_NPM_VERSION:-9.0.0}"
STUB
cat > npx-stub <<'STUB'
#!/bin/bash
printf 'npx %s cfg=%s cwd=%s pid=%s\n' "$*" "${CLAUDE_CONFIG_DIR-unset}" "$PWD" "$$" >> "$STUB_LOG"
if [ -n "${STUB_NPX_SLEEP:-}" ]; then exec sleep "$STUB_NPX_SLEEP"; fi
if [ -n "${STUB_NPX_SIGNAL:-}" ]; then kill -KILL $$; fi
if [ "${STUB_NPX_EXIT:-0}" = 0 ] && [ -z "${STUB_NPX_KEEP_MANIFEST:-}" ]; then
  config_directory="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  mkdir -p "$config_directory"
  printf '{"version":"%s"}' "${2#claude-dev-env@}" > "$config_directory/.claude-dev-env-manifest.json"
fi
exit "${STUB_NPX_EXIT:-0}"
STUB
chmod +x npm-stub npx-stub
for bin in bin bin-no-npm bin-no-npx bin-no-python bin-python-only; do mkdir "$bin"; ln -s "$(command -v node)" "$bin/node"; ln -s "$(command -v sleep)" "$bin/sleep"; done
for bin in bin bin-no-npm bin-no-npx; do ln -s "$(command -v python3)" "$bin/python3"; done
ln -s "$(command -v python3)" bin-python-only/python
for bin in bin bin-no-npx bin-no-python bin-python-only; do cp -p npm-stub "$bin/npm"; done
for bin in bin bin-no-npm bin-no-python bin-python-only; do cp -p npx-stub "$bin/npx"; done
cat > registration.py <<'PY'
import json
import sys

settings = json.load(open(sys.argv[1], encoding="utf-8"))
for group in settings.get("hooks", {}).get("SessionStart", []):
    for entry in group.get("hooks", []):
        if "session_start_refresh.py" in entry.get("command", ""):
            print(group.get("matcher", ""))
            print(entry.get("timeout", 60))
            print(entry["command"])
PY
cat > doctor.py <<'PY'
import shutil
import sys
from pathlib import Path

scratch, hooks_directory = sys.argv[1], sys.argv[2]
sys.path.insert(0, hooks_directory)
import session_start_refresh as hook

found = {"home": str(Path.home()), "config": str(hook.claude_config_directory())}
for tool in ("node", "python3", "python", "npm", "npx"):
    found[tool] = shutil.which(tool) or "absent"
outside = [name for name, value in found.items() if value != "absent" and not value.startswith(scratch + "/")]
for name, value in found.items():
    print(f"{name}={value}")
print("doctor: ready" if not outside else "doctor: not isolated: " + " ".join(outside))
sys.exit(1 if outside else 0)
PY
cat > drive <<'DRIVE'
#!/bin/bash
set -u
scratch=$(cd "$(dirname "$0")" && pwd -P) || exit 2
[ -f "$scratch/repository-root" ] || { echo "drive: run the seed block first"; exit 2; }
repository=$(cat "$scratch/repository-root")
evidence=$(cat "$scratch/evidence-root")
live_manifest=$(cat "$scratch/live-manifest-path")
doctor_python=$(cat "$scratch/doctor-python")
case_name=${1:?usage: drive <case> [--bin <folder>] [--manifest <text>] [--home-manifest <text>] [--failed-record <text>] [--in-progress-record <text>] [--kill-after <seconds>] [--doctor-only] [NAME=value ...]}
shift
bin_name=bin
manifest=
home_manifest=
failed_record=
in_progress_record=
kill_after=
doctor_only=
while [ $# -gt 0 ]; do
  case $1 in
    --bin) bin_name=$2; shift 2 ;;
    --manifest) manifest=$2; shift 2 ;;
    --home-manifest) home_manifest=$2; shift 2 ;;
    --failed-record) failed_record=$2; shift 2 ;;
    --in-progress-record) in_progress_record=$2; shift 2 ;;
    --kill-after) kill_after=$2; shift 2 ;;
    --doctor-only) doctor_only=1; shift ;;
    *) break ;;
  esac
done
git_before=$(git -C "$repository" status --porcelain --untracked-files=all --ignored) || { echo "drive: git status failed in $repository, hook not run"; exit 5; }
home="$scratch/homes/$case_name"
[ -e "$home" ] && { echo "drive: $home exists, pick a new case name"; exit 2; }
mkdir -p "$home/.claude"
tool_log="$scratch/homes/$case_name.tools.log"
case_evidence="$evidence/$case_name"
mkdir -p "$case_evidence"
hook_environment=(HOME="$home" USERPROFILE="$home" PATH="$scratch/$bin_name" PYTHONDONTWRITEBYTECODE=1 CLAUDE_PROJECT_DIR="$repository" STUB_LOG="$tool_log" "$@")
env -i "${hook_environment[@]}" "$doctor_python" -I -B "$scratch/doctor.py" "$scratch" "$repository/.claude/hooks" > "$case_evidence/doctor.txt" 2>&1
doctor_exit=$?
cat "$case_evidence/doctor.txt"
[ "$doctor_exit" -eq 0 ] || { echo "drive: doctor failed, hook not run"; exit 3; }
[ -n "$doctor_only" ] && exit 0
config_directory=$(sed -n 's/^config=//p' "$case_evidence/doctor.txt")
mkdir -p "$config_directory"
[ -n "$manifest" ] && printf '%s' "$manifest" > "$config_directory/.claude-dev-env-manifest.json"
[ -n "$home_manifest" ] && printf '%s' "$home_manifest" > "$home/.claude/.claude-dev-env-manifest.json"
[ -n "$failed_record" ] && printf '%s' "$failed_record" > "$config_directory/.claude-dev-env-refresh-failed-version"
[ -n "$in_progress_record" ] && printf '%s' "$in_progress_record" > "$config_directory/.claude-dev-env-refresh-in-progress"
mapfile -t registration < <("$doctor_python" -I "$scratch/registration.py" "$repository/.claude/settings.json")
[ "${#registration[@]}" -eq 3 ] || { echo "drive: no SessionStart entry names session_start_refresh.py"; exit 4; }
printf 'matcher=%s\ntimeout=%s\ncommand=%s\n' "${registration[@]}" > "$case_evidence/registration.txt"
live_hash() { if [ -f "$live_manifest" ]; then sha256sum "$live_manifest"; else echo "absent $live_manifest"; fi; }
live_before=$(live_hash)
: > "$tool_log"
started=$SECONDS
(cd "$repository" && printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}\n' "$repository" | timeout -s KILL "${kill_after:-${registration[1]}}" env -i "${hook_environment[@]}" /bin/bash -c "${registration[2]}" > "$case_evidence/stdout" 2> "$case_evidence/stderr")
hook_exit=$?
elapsed=$((SECONDS - started))
cp "$tool_log" "$case_evidence/tools.log"
live_after=$(live_hash)
git_after=$(git -C "$repository" status --porcelain --untracked-files=all --ignored)
{
  echo "case=$case_name exit=$hook_exit seconds=$elapsed stdout_bytes=$(wc -c < "$case_evidence/stdout") stderr_bytes=$(wc -c < "$case_evidence/stderr")"
  [ "$live_before" = "$live_after" ] && echo "live manifest unchanged: $live_after" || echo "LIVE MANIFEST CHANGED: $live_before -> $live_after"
  [ "$git_before" = "$git_after" ] && echo "repository status unchanged" || echo "REPOSITORY STATUS CHANGED"
  [ -s "$case_evidence/tools.log" ] || echo "tools: none"
  sed 's/^/tool: /' "$case_evidence/tools.log"
  sed 's/^/stdout: /' "$case_evidence/stdout"
  record="$config_directory/.claude-dev-env-refresh-failed-version"
  if [ -f "$record" ]; then echo "failed record: $(cat "$record")"; else echo "failed record: none"; fi
  progress_found=
  for progress in "$config_directory"/.claude-dev-env-refresh-in-progress*; do
    [ -f "$progress" ] || continue
    progress_found=1
    echo "in-progress record: $(cat "$progress")"
  done
  [ -n "$progress_found" ] || echo "in-progress record: none"
  manifest_now="$config_directory/.claude-dev-env-manifest.json"
  if [ -f "$manifest_now" ]; then echo "manifest: $(cat "$manifest_now")"; else echo "manifest: none"; fi
  for pid in $(sed -n 's/.* pid=\([0-9]*\)$/\1/p' "$case_evidence/tools.log"); do
    if kill -0 "$pid" 2>/dev/null; then echo "process $pid alive"; else echo "process $pid gone"; fi
  done
} | tee "$case_evidence/summary.txt"
DRIVE
chmod +x drive
live_manifest=$(cat live-manifest-path)
if [ -f "$live_manifest" ]; then sha256sum "$live_manifest"; else echo "absent $live_manifest"; fi | tee "$evidence/live-manifest-before.txt"
```

Each drive prints the doctor lines, then a summary that `<evidence>/<case>/summary.txt` keeps. A pass shows `doctor: ready`, `exit=0` unless the case names another exit, `stdout_bytes=0`, `failed record: none` and `in-progress record: none` unless the case names a message or a record, `live manifest unchanged`, and `repository status unchanged`. The `manifest:` line shows the home manifest after the hook. The npx stub writes `{"version":"<version>"}` there when it exits `0`, as the installer does, unless `STUB_NPX_KEEP_MANIFEST` is set. Each `stdout:` line repeats one line the hook printed. Each case name is used once, because every drive gets a new home.

- **Doctor.** Run `<scratch>/drive doctor --doctor-only CLAUDE_CODE_REMOTE=true`. Exit `0`. Each `home=`, `config=`, `node=`, `python3=`, `npm=`, and `npx=` line names a path under `<scratch>`, `python=absent`, and the last line is `doctor: ready`.
- **Doctor refusal.** Run `<scratch>/drive refusal --doctor-only CLAUDE_CONFIG_DIR="$HOME/.claude"`, which names the live configuration folder. Exit `3`, the line `doctor: not isolated: config`, and `drive: doctor failed, hook not run`.
- **Local guard.** Run `<scratch>/drive local --manifest '{"version":"8.0.0"}'`, then `<scratch>/drive remote-other --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=1`. Each shows `tools: none`.
- **Current install.** Run `<scratch>/drive current --manifest '{"version":"9.0.0"}' CLAUDE_CODE_REMOTE=true`. One line `tool: npm view claude-dev-env version cwd=<scratch>/homes/current pid=<n>`, and no `npx` line.
- **Registry ahead.** Run `<scratch>/drive stale --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The `npm view` line, then `tool: npx -y claude-dev-env@9.0.0 cfg=unset cwd=<scratch>/homes/stale pid=<n>`.
- **Registry behind.** Run `<scratch>/drive downgrade --manifest '{"version":"9.5.0"}' CLAUDE_CODE_REMOTE=true`. The `npm view` line, then `tool: npx -y claude-dev-env@9.0.0 cfg=unset cwd=<scratch>/homes/downgrade pid=<n>`.
- **Unusable manifest.** Run `<scratch>/drive no-manifest CLAUDE_CODE_REMOTE=true`, `<scratch>/drive not-json --manifest 'not json' CLAUDE_CODE_REMOTE=true`, `<scratch>/drive not-object --manifest '[1, 2]' CLAUDE_CODE_REMOTE=true`, and `<scratch>/drive number-version --manifest '{"version":9}' CLAUDE_CODE_REMOTE=true`. Each shows the `npx -y claude-dev-env@9.0.0` line.
- **Prerelease registry version.** Run `<scratch>/drive prerelease --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_VERSION=9.1.0-rc.1+build.5`. The line `tool: npx -y claude-dev-env@9.1.0-rc.1+build.5 ...`.
- **Configuration folder override.** Run `<scratch>/drive config-absolute --home-manifest '{"version":"8.0.0"}' --manifest '{"version":"9.0.0"}' CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR=<scratch>/profile-absolute`. Only the `npm view` line, because the hook reads `<scratch>/profile-absolute` and ignores the stale home manifest. Then run `<scratch>/drive config-relative CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR=profile` and `<scratch>/drive config-tilde CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR='~/profile'`. Their `config=` doctor lines and their `npx` lines show `<scratch>/homes/config-relative/profile` and `<scratch>/homes/config-tilde/profile`.
- **Probe fails.** Run `<scratch>/drive probe-exit --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_EXIT=1`. Only the `npm view` line, and one `stdout:` line with the lookup message that names `npx -y claude-dev-env@latest`.
- **Probe answer is not a bare version.** Run `<scratch>/drive probe-quoted --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_VERSION='"9.0.0"'`. Only the `npm view` line, and the lookup message. An npmrc `json=true` gives this answer.
- **No npm.** Run `<scratch>/drive no-npm --bin bin-no-npm --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The doctor shows `npm=absent`, the summary shows `tools: none`, and the lookup message.
- **No npx.** Run `<scratch>/drive no-npx --bin bin-no-npx --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. Only the `npm view` line, and one `stdout:` line with `9.0.0 did not install, because npx was not found on PATH or could not start`.
- **Install ends on a signal.** Run `<scratch>/drive install-signal --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_SIGNAL=1`. The `npx` line, one `stdout:` line with `stopped by signal 9`, and `failed record: none`.
- **Install exits 0 and leaves the old version.** Run `<scratch>/drive install-old --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_KEEP_MANIFEST=1`. The `npx` line, and one `stdout:` line with `exited 0, but the manifest shows 8.0.0 instead of 9.0.0`.
- **Hook stopped from outside.** Run `<scratch>/drive hook-stopped --manifest '{"version":"8.0.0"}' --kill-after 3 CLAUDE_CODE_REMOTE=true STUB_NPX_SLEEP=60`. `exit=137`, `seconds=3`, the `npx` line, `stdout_bytes=0`, `in-progress record: {"version": "9.0.0", "pid": <n>, ...}`, and `process <n> alive` on the `npx` line, because the install runs in its own session. Stop that process at cleanup.
- **Next start after a stopped hook.** Run `<scratch>/drive after-stop --manifest '{"version":"8.0.0"}' --in-progress-record 9.0.0 CLAUDE_CODE_REMOTE=true STUB_NPM_EXIT=1`. One `stdout:` line whose message holds two lines: `the refresh hook was stopped at an earlier session start before its install of 9.0.0 ended`, then the lookup message. `in-progress record: none`. Then run `<scratch>/drive after-stop-done --manifest '{"version":"9.0.0"}' --in-progress-record 9.0.0 CLAUDE_CODE_REMOTE=true`, where the left install finished. `stdout_bytes=0` and `in-progress record: none`. Then run `<scratch>/drive after-stop-later --manifest '{"version":"8.0.0"}' --in-progress-record 9.0.0 CLAUDE_CODE_REMOTE=true STUB_NPM_VERSION=9.1.0`, where this start installs a later release. The `npx -y claude-dev-env@9.1.0` line, `stdout_bytes=0`, and `in-progress record: none`.
- **Hook error.** Run `<scratch>/drive hook-error --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR=<scratch>/repository-root`, which names a file as the configuration folder. The drive cannot write the manifest there, and the hook finds no records there. `exit=0`, only the `npm view` line, and one `stdout:` line with `the refresh hook stopped on FileExistsError`, raised when the hook creates the folder for its in-progress record.
- **Install fails.** Run `<scratch>/drive install-exit --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_EXIT=1`. The `npx` line, `exit=0`, one `stdout: {"systemMessage": "claude-dev-env refresh: `npx -y claude-dev-env@9.0.0` failed with exit code 1, ...` line, and `failed record: 9.0.0`.
- **Failed version skipped.** Run `<scratch>/drive install-skip --manifest '{"version":"8.0.0"}' --failed-record 9.0.0 CLAUDE_CODE_REMOTE=true`. Only the `npm view` line, one `stdout: {"systemMessage": "claude-dev-env refresh: skipped 9.0.0, ...` line that names `npx -y claude-dev-env@9.0.0`, and `failed record: 9.0.0`.
- **Next release after a failed one.** Run `<scratch>/drive install-next --manifest '{"version":"8.0.0"}' --failed-record 8.5.0 CLAUDE_CODE_REMOTE=true`. The `npx -y claude-dev-env@9.0.0` line, `stdout_bytes=0`, and `failed record: 8.5.0`.
- **Probe timeout.** Run `<scratch>/drive probe-timeout --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_SLEEP=120`. `seconds=30` or `31`, only the `npm view` line, the lookup message, and `process <n> gone`.
- **Install timeout.** Start `<scratch>/drive install-timeout --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_SLEEP=900` in the background, because it runs about 570 seconds. Run the other cases while it waits, because each drive writes its own tool log. `seconds=570` or `571`, the `npx` line, one `stdout:` line with `ran past 570 seconds and was stopped`, `failed record: none`, `in-progress record: none`, and `process <n> gone` on both process lines. `tests/test_session_start_refresh.py` covers the same outcome in about a second on a copy of the hook folder whose limit is 1 second.
- **Python fallback.** Run `<scratch>/drive python-fallback --bin bin-python-only --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The doctor shows `python3=absent`, and the summary shows the `npx` line.
- **No Python.** Run `<scratch>/drive no-python --bin bin-no-python --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. `exit=1` and `tools: none`. Claude Code treats an exit other than `0` or `2` as a non-blocking hook error, so the session starts without the refresh.
- **Broken `config/`.** Seed a new `<scratch>` against a git copy of the hook folder, then delete the `INSTALL_TIMEOUT_SECONDS` line from the copy's `.claude/hooks/config/session_start_refresh_constants.py`. Run `<scratch>/drive broken-config CLAUDE_CODE_REMOTE=true`. The doctor prints `ImportError: cannot import name 'INSTALL_TIMEOUT_SECONDS'`, then `drive: doctor failed, hook not run`, and the drive exits `3`.
- **Proof.** Run `sha256sum "$(cat <scratch>/live-manifest-path)"` and compare it with `<evidence>/live-manifest-before.txt`. Keep `<evidence>`, which holds `live-manifest-before.txt` and one folder per case. A case that ran the hook holds `doctor.txt`, `registration.txt`, `stdout`, `stderr`, `tools.log`, and `summary.txt`. A `--doctor-only` case holds `doctor.txt` only.
- **Cleanup.** Read `<evidence>/*/summary.txt` for a `process <n> alive` line, and stop only those process IDs. Then remove `<scratch>` with one `rm -r` on its literal absolute path. Run `ls <evidence>` to confirm the evidence is still there.

## Gotchas

- Silence is the pass only for a current install and for an install that brings the manifest to the registry version. Every other remote branch prints one `systemMessage` line. The hook sends install output to `/dev/null`, so the stub log is the only record of what ran. Read `tools.log`, and check the exit code before you trust empty output.
- The drive shows the line the hook prints. It does not show Claude Code displaying that `systemMessage`. A cloud session start on this repository with a failing install proves the display.
- The stubs stand in for the registry, the published installer, and the manifest the installer rewrites. A drive proves the hook's decisions, and it does not prove that an install succeeds. Use [Installer lifecycle](installer-lifecycle.md) for the install itself.
- The driver runs the registered command with a `startup` payload and the registered timeout. Claude Code's matcher and its own timeout are not driven. A change to the matcher needs a session start on the web to prove it.
- A non-zero install exit leaves the manifest at the old version. The failed record stops the next session start from running the same version again, and it stays until a release with another version comes out. The failed record lives as long as the manifest beside it does.
- The install timeout kills the installer's process group after 570 seconds, wherever the installer is in its writes. It prints the timeout message and writes no failed record, so the next start runs the install again over the partial tree.
- A hook killed from outside cannot print. Its in-progress record is the only trace, and the next start reports it. Two starts that overlap in one home each write their own record, and the second start leaves the first one's record alone while that run's process lives. When a new process reuses a stopped run's process id, the start reports that run once its record is 630 seconds old. A hook in another process id namespace that shares the folder reads as stopped.
- The seed block is longer than 4096 characters and holds shell variables. A session that also loads another repository's Bash gates can refuse a command of that shape, so run the block from a saved file. Those gates also refuse a command whose program name starts with a variable, such as `"$scratch/drive"`. Call the driver by its literal path.
- `CLAUDE_CODE_REMOTE=true` comes from the cloud session. The driver's `env -i` drops it, so pass it on each remote case.
- `CLAUDE_CONFIG_DIR` with an absolute path outside `<scratch>` stops at the doctor. Keep every override under `<scratch>`, or relative to the scratch home.
- On Windows the launcher tries `py -3`, then `python`. This recipe covers the POSIX launcher order only.
- `tests/test_session_start_refresh.py` runs the same decisions under pytest with stubs. From `<repository>`, run `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp <scratch>/pytest-tmp tests/test_session_start_refresh.py` beside the drive, which leaves no `.pytest_cache` or `__pycache__` in the checkout. `--basetemp` empties its folder first, so name a folder that holds nothing else. The test runs the hook with a copy of the session environment, minus `CLAUDE_CODE_REMOTE` and `CLAUDE_CONFIG_DIR`, with its `npm` and `npx` shims put in front of the session `PATH`, where the drive builds the environment from `env -i` with a `PATH` of scratch links only.
