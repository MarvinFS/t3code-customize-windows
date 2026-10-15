# Porting the patches to a new T3 Code nightly

These instructions are for a coding agent. A person can follow them too.

The patches in `patches/` are commits made against the upstream commit in
`patches/base.txt`. Upstream moves fast, so they often stop applying cleanly. Your job
is to carry them onto the user's nightly with every feature still working.

## Start

1. Run `./t3code-customize build` from this repo. It finds the installed AppImage,
   reads the exact upstream commit it was built from, and applies the patches to
   that commit in the source checkout at `~/.cache/t3code-customize/t3code`.
2. If it reports a conflict, a rebase is stopped in that checkout. If it reports a
   failing test or typecheck, the commits are in place and the checks failed.

## Fix

Work only in `~/.cache/t3code-customize/t3code` and this repo.

- Conflicts: resolve each file, `git add` it, then `GIT_EDITOR=true git rebase --continue`.
  Keep upstream's change and port the patch on top of it. When upstream moved or split
  a file, carry the change to the new location and follow the new APIs.
- Failing checks: fix the relevant commit with `git commit --fixup=<sha>`, then
  `GIT_SEQUENCE_EDITOR=true git rebase -i --autosquash <nightly commit>`. Keep one
  commit per patch.
- If a test file moved upstream, update its path in `checks.json`.
- `git log <base>..<nightly commit>` and `git show` explain what changed upstream.
- To install dependencies, use exactly `pnpm install --frozen-lockfile --ignore-scripts`
  in the source checkout, the same as the tool.

Do not drop a patch, delete or weaken a test, or skip a check to get green. If a
feature can't be ported sensibly, stop and explain why.

## Finish

If `t3code-customize` started you, stop once the tests and typechecks in `checks.json`
pass (run them from the source checkout with `node_modules/.bin/vp test run <files>` and
`node_modules/.bin/tsc-rs --noEmit -p <package>/tsconfig.json`). It continues the build itself.

Otherwise run `./t3code-customize build --resume`. It reruns the checks on the checkout as you
left it, builds, installs the result and writes the ported commits back to
`patches/`. Leave the checkout clean with no rebase in progress.

End with a short report: what changed upstream, what you changed and in which files,
and whether the final build succeeded.

## Windows

The same steps apply. Differences:

- The source checkout is `%LOCALAPPDATA%\t3code-customize\cache\t3code`, logs are in `...\cache\logs`.
- Run the checks from the checkout with `node_modules\.bin\vp.CMD test run <files>` and `node_modules\.bin\tsc-rs.CMD --noEmit -p <package>\tsconfig.json`, or call `node_modules/.bin/vp` from Git Bash.
- Keep LF line endings: `git config core.autocrlf` must stay `false` in the checkout, and `patches/` is marked `-text` so `git am` sees the exact bytes.
- Run `python t3code-customize build --resume` (add `--install-dir <folder>` if T3 Code is not under `%LOCALAPPDATA%\Programs`).
- The scheduled task never starts an agent. Port by hand or run `python t3code-customize --fix claude` yourself; the next unattended run picks up the ported `patches/`.
