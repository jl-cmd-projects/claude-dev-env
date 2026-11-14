# Repository `.claude/hooks`

This repository's own `.claude/settings.json` registers one SessionStart hook for sessions opened on this checkout. At a cloud session start, `.claude/hooks/session_start_refresh.py` compares the installed `claude-dev-env` version with the npm registry version. When they differ, it runs `npx -y claude-dev-env@<registry version>`. The hook prints nothing, and every path through it exits `0`. [The cloud session guide](../../../../docs/claude-code-on-the-web.md) states why the hook exists. The package hooks have their own map in [Hook lifecycle](hook-lifecycle.md).

## Sub-features

- `registration`. The SessionStart group with matcher `startup|resume` runs `node .claude/hooks/python_script_launcher.js .claude/hooks/session_start_refresh.py` with timeout `630`.
- `launcher`. `python_script_launcher.js` starts `python3`, then `python` (`py -3`, then `python`, on Windows), and returns the script's exit code. With no Python on `PATH`, it exits `1`.
- `local-guard`. A `CLAUDE_CODE_REMOTE` value other than `true` exits before any tool call.
- `current-install`. A manifest version equal to the registry version costs one `npm view claude-dev-env version` call and runs no install.
- `stale-install`. An older or missing manifest version runs `npx -y claude-dev-env@<registry version>`. So does a manifest that is not JSON, not an object, or has no string `version`. Both calls run from the home directory.
- `config-dir`. `CLAUDE_CONFIG_DIR` moves the manifest the hook reads. A relative or `~` value anchors to the home directory. The install gets the resolved absolute path in `CLAUDE_CONFIG_DIR`.
- `fail-open`. These cases exit `0` with no install: no `npm`, a non-zero `npm` exit, a registry answer that is not a bare version, and a probe past 30 seconds. These cases exit `0` after the install starts or is skipped: no `npx`, a non-zero install exit, and an install past 570 seconds. A timeout kills the tool's process group.

## How to get to it (user POV)

- Open a Claude Code session on this repository on the web, where `CLAUDE_CODE_REMOTE=true` is set. A `startup` or `resume` start runs the hook. A `clear` or `compact` start does not.
- Change a file under `.claude/hooks/`, or the SessionStart entry in `.claude/settings.json`. The next session start runs the changed code.

## Driving it with the scratch driver

Preconditions:

- A Linux shell has `bash`, `node`, `python3`, `sleep`, `timeout`, `sha256sum`, and `git` on `PATH`.
- `<repository>` is the absolute path of this checkout.
- `<scratch>` is a new absolute path under the OS temporary root, such as `/tmp/claude-hooks-verify-<run id>`. The seed block refuses a path that exists.
- `<evidence>` is an absolute path outside `<scratch>` and outside the repository, such as a folder in the session scratchpad. Keep this feature's proof in `<evidence>`. The evidence folder that `SKILL.md` names is for the installer transcript.

**Isolation rule.** Run the hook only through `<scratch>/drive`. Never run the registered command, `session_start_refresh.py`, or `python_script_launcher.js` with the session's own environment. A cloud session sets `CLAUDE_CODE_REMOTE=true`, so that run asks the registry for a version and can run the published installer over the live `~/.claude` tree. The driver builds the hook's environment from empty with `env -i`. `HOME` and `USERPROFILE` are a new folder under `<scratch>/homes/`. `PATH` is one `<scratch>/bin*` folder that holds links to `node`, `python3`, and `sleep`, plus `npm` and `npx` stubs that only append a line to a log. `PYTHONDONTWRITEBYTECODE=1` keeps `__pycache__` out of `.claude/hooks`. Before each drive, the driver runs a doctor under the same environment. The doctor stops the drive with exit `3` when the home, the configuration folder the hook resolves, or a tool on `PATH` is outside `<scratch>`. Each drive also hashes the live manifest and reads `git status` before and after the hook.

Seed the scratch folder once. Save the block to a file outside the repository, such as `<evidence>-seed.sh`. Set the three paths on its first three lines, then run `bash <evidence>-seed.sh`:

```bash
scratch=/tmp/claude-hooks-verify-run1
evidence=/abs/path/to/evidence
repository=/abs/path/to/claude-dev-env
mkdir "$scratch" || exit 1
mkdir -p "$evidence" "$scratch/homes"
cd "$scratch" || exit 1
printf '%s\n' "$repository" > repository-root
printf '%s\n' "$evidence" > evidence-root
command -v python3 > doctor-python
python3 -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import session_start_refresh as hook; print(hook.claude_config_directory() / hook.MANIFEST_FILE_NAME)' "$repository/.claude/hooks" > live-manifest-path
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
case_name=${1:?usage: drive <case> [--bin <folder>] [--manifest <text>] [--home-manifest <text>] [--doctor-only] [NAME=value ...]}
shift
bin_name=bin
manifest=
home_manifest=
doctor_only=
while [ $# -gt 0 ]; do
  case $1 in
    --bin) bin_name=$2; shift 2 ;;
    --manifest) manifest=$2; shift 2 ;;
    --home-manifest) home_manifest=$2; shift 2 ;;
    --doctor-only) doctor_only=1; shift ;;
    *) break ;;
  esac
done
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
mapfile -t registration < <("$doctor_python" -I "$scratch/registration.py" "$repository/.claude/settings.json")
[ "${#registration[@]}" -eq 3 ] || { echo "drive: no SessionStart entry names session_start_refresh.py"; exit 4; }
printf 'matcher=%s\ntimeout=%s\ncommand=%s\n' "${registration[@]}" > "$case_evidence/registration.txt"
live_hash() { if [ -f "$live_manifest" ]; then sha256sum "$live_manifest"; else echo "absent $live_manifest"; fi; }
live_before=$(live_hash)
git_before=$(git -C "$repository" status --porcelain)
: > "$tool_log"
started=$SECONDS
(cd "$repository" && printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}\n' "$repository" | timeout "${registration[1]}" env -i "${hook_environment[@]}" /bin/bash -c "${registration[2]}" > "$case_evidence/stdout" 2> "$case_evidence/stderr")
hook_exit=$?
elapsed=$((SECONDS - started))
cp "$tool_log" "$case_evidence/tools.log"
live_after=$(live_hash)
git_after=$(git -C "$repository" status --porcelain)
{
  echo "case=$case_name exit=$hook_exit seconds=$elapsed stdout_bytes=$(wc -c < "$case_evidence/stdout") stderr_bytes=$(wc -c < "$case_evidence/stderr")"
  [ "$live_before" = "$live_after" ] && echo "live manifest unchanged: $live_after" || echo "LIVE MANIFEST CHANGED: $live_before -> $live_after"
  [ "$git_before" = "$git_after" ] && echo "repository status unchanged" || echo "REPOSITORY STATUS CHANGED"
  [ -s "$case_evidence/tools.log" ] || echo "tools: none"
  sed 's/^/tool: /' "$case_evidence/tools.log"
  for pid in $(sed -n 's/.* pid=\([0-9]*\)$/\1/p' "$case_evidence/tools.log"); do
    if kill -0 "$pid" 2>/dev/null; then echo "process $pid alive"; else echo "process $pid gone"; fi
  done
} | tee "$case_evidence/summary.txt"
DRIVE
chmod +x drive
live_manifest=$(cat live-manifest-path)
if [ -f "$live_manifest" ]; then sha256sum "$live_manifest"; else echo "absent $live_manifest"; fi | tee "$evidence/live-manifest-before.txt"
```

Each drive prints the doctor lines, then a summary that `<evidence>/<case>/summary.txt` keeps. A pass shows `doctor: ready`, `exit=0`, `stdout_bytes=0`, `live manifest unchanged`, and `repository status unchanged`. Each case name is used once, because every drive gets a new home.

- **Doctor.** Run `<scratch>/drive doctor --doctor-only CLAUDE_CODE_REMOTE=true`. Exit `0`. Each `home=`, `config=`, `node=`, `python3=`, `npm=`, and `npx=` line names a path under `<scratch>`, `python=absent`, and the last line is `doctor: ready`.
- **Doctor refusal.** Run `<scratch>/drive refusal --doctor-only CLAUDE_CONFIG_DIR="$HOME/.claude"`, which names the live configuration folder. Exit `3`, the line `doctor: not isolated: config`, and `drive: doctor failed, hook not run`.
- **Local guard.** Run `<scratch>/drive local --manifest '{"version":"8.0.0"}'`, then `<scratch>/drive remote-other --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=1`. Each shows `tools: none`.
- **Current install.** Run `<scratch>/drive current --manifest '{"version":"9.0.0"}' CLAUDE_CODE_REMOTE=true`. One line `tool: npm view claude-dev-env version cwd=<scratch>/homes/current pid=<n>`, and no `npx` line.
- **Registry ahead.** Run `<scratch>/drive stale --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The `npm view` line, then `tool: npx -y claude-dev-env@9.0.0 cfg=unset cwd=<scratch>/homes/stale pid=<n>`.
- **Unusable manifest.** Run `<scratch>/drive no-manifest CLAUDE_CODE_REMOTE=true`, `<scratch>/drive not-json --manifest 'not json' CLAUDE_CODE_REMOTE=true`, `<scratch>/drive not-object --manifest '[1, 2]' CLAUDE_CODE_REMOTE=true`, and `<scratch>/drive number-version --manifest '{"version":9}' CLAUDE_CODE_REMOTE=true`. Each shows the `npx -y claude-dev-env@9.0.0` line.
- **Prerelease registry version.** Run `<scratch>/drive prerelease --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_VERSION=9.1.0-rc.1+build.5`. The line `tool: npx -y claude-dev-env@9.1.0-rc.1+build.5 ...`.
- **Configuration folder override.** Run `<scratch>/drive config-absolute --home-manifest '{"version":"8.0.0"}' --manifest '{"version":"9.0.0"}' CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR=<scratch>/profile-absolute`. Only the `npm view` line, because the hook reads `<scratch>/profile-absolute` and ignores the stale home manifest. Then run `<scratch>/drive config-relative CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR=profile` and `<scratch>/drive config-tilde CLAUDE_CODE_REMOTE=true CLAUDE_CONFIG_DIR='~/profile'`. Their `config=` doctor lines and their `npx` lines show `<scratch>/homes/config-relative/profile` and `<scratch>/homes/config-tilde/profile`.
- **Probe fails.** Run `<scratch>/drive probe-exit --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_EXIT=1`. Only the `npm view` line.
- **Probe answer is not a bare version.** Run `<scratch>/drive probe-quoted --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_VERSION='"9.0.0"'`. Only the `npm view` line. An npmrc `json=true` gives this answer.
- **No npm.** Run `<scratch>/drive no-npm --bin bin-no-npm --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The doctor shows `npm=absent`, and the summary shows `tools: none`.
- **No npx.** Run `<scratch>/drive no-npx --bin bin-no-npx --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. Only the `npm view` line.
- **Install fails.** Run `<scratch>/drive install-exit --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_EXIT=1`. The `npx` line and `exit=0`.
- **Probe timeout.** Run `<scratch>/drive probe-timeout --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPM_SLEEP=120`. `seconds=30` or `31`, only the `npm view` line, and `process <n> gone`.
- **Install timeout.** Start `<scratch>/drive install-timeout --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true STUB_NPX_SLEEP=900` in the background, because it runs about 570 seconds. Run the other cases while it waits, because each drive writes its own tool log. `seconds=570` or `571`, the `npx` line, and `process <n> gone` on both process lines.
- **Python fallback.** Run `<scratch>/drive python-fallback --bin bin-python-only --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. The doctor shows `python3=absent`, and the summary shows the `npx` line.
- **No Python.** Run `<scratch>/drive no-python --bin bin-no-python --manifest '{"version":"8.0.0"}' CLAUDE_CODE_REMOTE=true`. `exit=1` and `tools: none`. Claude Code treats an exit other than `0` or `2` as a non-blocking hook error, so the session starts without the refresh.
- **Proof.** Run `sha256sum "$(cat <scratch>/live-manifest-path)"` and compare it with `<evidence>/live-manifest-before.txt`. Keep `<evidence>`, which holds `live-manifest-before.txt` and one folder per case. A case that ran the hook holds `doctor.txt`, `registration.txt`, `stdout`, `stderr`, `tools.log`, and `summary.txt`. A `--doctor-only` case holds `doctor.txt` only.
- **Cleanup.** Read `<evidence>/*/summary.txt` for a `process <n> alive` line, and stop only those process IDs. Then remove `<scratch>` with one `rm -r` on its literal absolute path. Run `ls <evidence>` to confirm the evidence is still there.

## Gotchas

- Silence is the pass for every branch. The hook sends install output to `/dev/null` and prints nothing, so the stub log is the only record of what ran. Read `tools.log`, and check the exit code before you trust empty output.
- The stubs stand in for the registry, the published installer, and the manifest the installer rewrites. A drive proves the hook's decisions, and it does not prove that an install succeeds. Use [Installer lifecycle](installer-lifecycle.md) for the install itself.
- The driver runs the registered command with a `startup` payload and the registered timeout. Claude Code's matcher and its own timeout are not driven. A change to the matcher needs a session start on the web to prove it.
- A non-zero install exit leaves the manifest at the old version, so the next session start runs the install again.
- The install timeout kills the installer's process group after 570 seconds, wherever the installer is in its writes.
- The seed block is longer than 4096 characters and holds shell variables. A session that also loads another repository's Bash gates can refuse a command of that shape, so run the block from a saved file. Those gates also refuse a command whose program name starts with a variable, such as `"$scratch/drive"`. Call the driver by its literal path.
- `CLAUDE_CODE_REMOTE=true` comes from the cloud session. The driver's `env -i` drops it, so pass it on each remote case.
- `CLAUDE_CONFIG_DIR` with an absolute path outside `<scratch>` stops at the doctor. Keep every override under `<scratch>`, or relative to the scratch home.
- On Windows the launcher tries `py -3`, then `python`. This recipe covers the POSIX launcher order only.
- `tests/test_session_start_refresh.py` runs the same decisions under pytest with stubs. Run `pytest tests/test_session_start_refresh.py -q` beside the drive.
