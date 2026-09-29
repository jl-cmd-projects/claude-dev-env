# Release and publish

`.github/workflows/publish.yml` turns merged commits on `main` into an npm release. Its `release` job runs release-please with `release-please-config.json` and `.release-please-manifest.json`. The job opens or refreshes one release pull request, and when that pull request merges it cuts the `claude-dev-env-v<version>` tag and the GitHub release. The `publish` job then runs `npm publish` from `packages/claude-dev-env` and waits for the version on the npm registry.

Every check below reads live state or packs the tarball locally. None of them publishes, tags, or merges.

## Sub-features

- `release-pr` opens or refreshes the pull request titled `chore(main): release claude-dev-env <next version>` on the branch `release-please--branches--main--components--claude-dev-env`. It bumps `package.json`, the manifest, and `CHANGELOG.md`.
- `release-pr-checks` posts a passing check run for each required context of the `main` branch rules on the release pull request head. release-please pushes with the workflow token, so the pull request workflows never start on that head.
- `release-pr-merge` merges the release pull request when its diff touches only the manifest, `package.json`, and `CHANGELOG.md`, then dispatches `publish.yml` on `main`. A merge made with the workflow token starts no push run, so the dispatch cuts the tag and publishes.
- `tag-and-release` runs when the release pull request merges. The `release` job sets `packages/claude-dev-env--release_created` to `true`, and GitHub holds the tag and release at the merge commit.
- `npm-publish` runs `npm publish --access public` with the `id-token: write` permission. It runs after a release, or on a manual `workflow_dispatch`.
- `registry-wait` polls `https://registry.npmjs.org/claude-dev-env/<version>` every 10 seconds, 60 times.
- `daily-schedule` runs the whole workflow at 12:00 UTC.

## How to get to it (user POV)

- A maintainer merges a feature pull request into `main`. The workflow runs on the push and refreshes the release pull request.
- The workflow merges the release pull request and dispatches the next run, which tags, releases, and publishes.
- A user runs `npx claude-dev-env` or installs the package and gets the new version.

## Driving it with curl, npm, and git

Preconditions:

- Commands run from the repository root, with `origin/main` fetched.
- `curl`, `node`, `npm`, and `git` are on the path. The GitHub reads are anonymous, so no token is needed for a public repository.

- **Version chain.** Each command prints one version. They agree after a finished release.

  ```bash
  node -p 'require("./.release-please-manifest.json")["packages/claude-dev-env"]'
  node -p 'require("./packages/claude-dev-env/package.json").version'
  sed -n 3p packages/claude-dev-env/CHANGELOG.md
  git ls-remote --tags origin 'claude-dev-env-v*' | sort -t v -k 3 -V | tail -1
  curl -sS https://api.github.com/repos/jl-cmd/claude-dev-env/releases/latest | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s).tag_name))'
  npm view claude-dev-env version
  ```

  The manifest, `package.json`, the `CHANGELOG.md` heading, the newest tag, the latest release, and `npm view` all name the same version. A tag or release ahead of npm means `publish` failed. npm ahead of the manifest means a publish ran outside this workflow.

- **Release pull request.** Read the open pull request and the checks on its head:

  ```bash
  curl -sS 'https://api.github.com/repos/jl-cmd/claude-dev-env/pulls?state=open&head=jl-cmd:release-please--branches--main--components--claude-dev-env' | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const p of JSON.parse(s))console.log(p.number,p.title,p.head.sha)})'
  curl -sS 'https://api.github.com/repos/jl-cmd/claude-dev-env/commits/<head sha>/check-runs?per_page=100' | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const c of JSON.parse(s).check_runs)console.log(c.name,"|",c.conclusion,"|",c.output.title)})'
  ```

  One pull request prints, titled `chore(main): release claude-dev-env <next version>`. Each required context of the `main` rules prints with `success` and the title `Release pull request`. Compare the list with `curl -sS https://api.github.com/repos/jl-cmd/claude-dev-env/rules/branches/main`.

- **Workflow jobs.** Read one run's jobs by id from the workflow runs list:

  ```bash
  curl -sS 'https://api.github.com/repos/jl-cmd/claude-dev-env/actions/workflows/publish.yml/runs?per_page=10' | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const r of JSON.parse(s).workflow_runs)console.log(r.id,r.event,r.conclusion,r.display_title.slice(0,70))})'
  curl -sS https://api.github.com/repos/jl-cmd/claude-dev-env/actions/runs/<run id>/jobs | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const j of JSON.parse(s).jobs)console.log(j.name,"|",j.conclusion)})'
  ```

  A feature merge shows `release` and the check job with `success` and `publish` with `skipped`. A release merge shows `publish` with `success`, or `failure` at `Verify npm package availability` per the gotcha below.

- **Tarball.** Pack the package without sending it:

  ```bash
  cd packages/claude-dev-env && npm publish --dry-run --access public
  ```

  The command exits `0`. The last lines read `name: claude-dev-env`, the manifest version, `total files: <count>`, and `Publishing to https://registry.npmjs.org/ with tag latest and public access (dry-run)`. Read the file list for a path the change added or removed. The `files` list in `package.json` decides what ships.

## Gotchas

- `registry-wait` gives up after 600 seconds. The registry has taken over 300 seconds to serve the version document. The 8.21.0 run failed at 11:42:49 UTC, and npm records 8.21.0 at 11:42:50 UTC. A red `publish` job at that step with the version on npm afterwards is a published release. Read `npm view claude-dev-env@<version> version` before any retry.
- A second `npm publish` of a version already on npm fails. Rerun `publish` only when `npm view` reports the version missing.
- The release pull request body is input for release-please. Editing its body or title stops release-please from recognizing the merge, so no tag is cut and nothing publishes.
- The branch rules can require an extra approving review for changes without an attributed author. With that setting on, the bot-authored release pull request waits on a maintainer approval, and `release-pr-merge` logs a notice and leaves it open.
- Approving the held pull request workflows on the release head starts runs that replace the posted passing checks with pending ones. Leave them unapproved.
- The strict required-checks policy needs an up-to-date head. release-please rebuilds the release pull request on every push to `main`, and `release-pr-checks` posts fresh check runs on each new head.
- `npm publish --dry-run` warns `This command requires you to be logged in` and still exits `0`. The warning is expected in a sandbox without npm credentials.
- The workflow `concurrency` group queues runs in order. A manual dispatch waits for the push run ahead of it.
