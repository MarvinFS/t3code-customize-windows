# t3code-customize on Windows

Windows port of [btsouth/t3code-customize](https://github.com/btsouth/t3code-customize). It puts your 5 hour and weekly usage, context and tokens per second under the T3 Code composer. Patches 0001 to 0003 come from btsouth and are ported here when a nightly moves the code they touch. Beside them sit two more of his (a model-switch suggestion and a fix that lets one test run on Windows) and two that exist only in this repo (the Monitor roster fix and the skill rows); see the table in `.github/README.md`. Only `t3code-customize` knows about Windows. The repo root `README.md` is btsouth's own, kept as he wrote it; the Windows docs are this file and `.github/README.md`.

## What it needs

T3 Code Nightly installed for the current user, Python 3.12 or newer, git, and Node 24 or newer with pnpm on the PATH. Long paths must be on (`LongPathsEnabled=1`, the default on a current Windows 11 install). A build uses about 6 GB under `%LOCALAPPDATA%\t3code-customize`.

Stable T3 Code (the "Alpha" product, 0.0.45 at the time of writing) is refused with a message: the patches target the Nightly line.

## Moving from stable to Nightly

The Nightly installer uses the same app id as stable, so it upgrades the existing install in place; it does not sit beside it. Both use the same data folders (`%APPDATA%\t3code-v2` and `~\.t3`), so threads and settings carry over. Nightly can migrate that data forward, and stable may not read it afterwards, so copy `~\.t3` somewhere first.

1. Quit T3 Code fully, then copy its data: `Copy-Item $HOME\.t3 $HOME\.t3-backup -Recurse` (about 300 MB).
2. Switch the update channel to Nightly in the app (Settings, "Use stable releases or nightly builds"), or run `T3-Code-<version>-x64.exe` from the [releases page](https://github.com/pingdotgg/t3code/releases) (the newest `-nightly.` tag).
3. Open it once and check the threads are there, then quit it.

## Install

```powershell
git clone https://github.com/MarvinFS/t3code-customize-windows C:\code\t3code-customize-windows
python C:\code\t3code-customize-windows\t3code-customize
python C:\code\t3code-customize-windows\t3code-customize schedule
```

The first run clones T3 Code's source and installs build dependencies, so allow 10 to 20 minutes. It then adds `t3code-customize.cmd` to `%LOCALAPPDATA%\Microsoft\WindowsApps` (already on the PATH) and a Start Menu shortcut named "T3 Code (Customized)". Open T3 Code from that shortcut and turn on Settings > General > Stats for nerds.

## Checks

Before a build the tool applies the patches to the nightly's exact upstream commit and runs, all at once, the test files and package typechecks listed in `checks.json`: `vp test run` over 21 test files, and `tsc --noEmit -p <package>/tsconfig.json` over 8 packages. In the checkout `tsc` is tsc-rs, Theo Browne's Rust port of the TypeScript 7 compiler: since upstream #23023 (2026-10-22) the `typescript` package resolves to `@tsc-rs/typescript` and T3 Code's own `typecheck` scripts call `tsc`. Before that the binary was named `tsc-rs`, which the tool called from 2026-10-15; before that it ran the official `tsc` 7.0.2.

Measured that day on this PC, the 8 typechecks together took 24 to 26 seconds with `tsc` and 10 seconds with `tsc-rs`, with 0 errors from both. An injected type error was caught by both with the same message, and only the exit code differs (1 against 2). `tsc-rs` also prints Effect language-service suggestions into the log, about 150 lines for `apps/server`; they do not fail the build. The test step takes longer than either compiler, so a build is not 15 seconds faster. `tsc-rs` reports itself as 7.1.0-dev.

`checks.windows.json` lists tests that fail on Windows for a reason that is not a patch regression, each with its reason, and a build continues when only those fail. Any other failure stops it. Today that is one upstream test that looks for the Unix path `/synthetic/project` (it passes on the current nightly), and the upstream steer test "moves the root's foreground subagents to the background before a steer (never answers)", which also fails on unpatched upstream here. The two permission-bit assertions that patch 0002 adds used to be on the list; btsouth's file-mode patch makes them expect Windows modes, so they run now.

## Keeping it current

`schedule` registers the task `t3code-customize`. It runs at sign-in and every hour, without a window. Each run fetches upstream's latest patches, compares the installed `app.asar` and `server.asar` with the last build, and does nothing when neither changed. When T3 Code updates itself, the next run rebuilds and shows a notification. Until then the shortcut opens stock T3 Code and says why.

T3 Code downloads an update well before it installs it (the tray's "restart to install"). When a run finds such a download, it unpacks the app from it with 7-Zip and builds for that version ahead, leaving the installed app alone, and notifies you. Once that version is installed, by the tray or by an install request (below), the next run takes the build made ahead instead of building again, after checking that the installed `app.asar` and `server.asar` are byte for byte the ones it built from.

T3 can also be updated on request. When a file named `install-update` exists in `%LOCALAPPDATA%\t3code-customize` and is less than 10 minutes old, the next run quits T3 Code, checks the download against the sha512 T3 recorded, installs it silently with the flags T3's updater uses, takes or makes the build, and opens "T3 Code (Customized)" again. Create the file and run `Start-ScheduledTask t3code-customize` to ask. The work happens in the task, so it survives T3 closing even when you start it from T3's own terminal.

If a nightly breaks the patches the run stops, tells you once, and waits 6 hours (or until upstream ships new patches) before trying again. Your installed T3 Code is never touched. To have the task port them itself, register it with an agent: `t3code-customize schedule --fix claude` (or `codex`). The agent then runs inside the task with full permissions, at most 35 minutes per attempt and two attempts; its checks must pass before anything is built, and if it cannot port them the run stops as above. The progress of unattended runs is in `%LOCALAPPDATA%\t3code-customize\cache\unattended.log`.

Commands: `t3code-customize` (build now), `status`, `off`, `on`, `pack`, `schedule`, `unschedule`, `uninstall`, `launch`. `--install-dir` points at a T3 Code folder when it is not under `%LOCALAPPDATA%\Programs`. `pack` zips the two patched asars of the current build into `%LOCALAPPDATA%\t3code-customize\packs` for installing by hand (see "Install without building" in `.github/README.md`). Old builds are pruned after each build, keeping the current one, the one made ahead and the one before the current; `pack` keeps the current and the previous zip. To publish every build as a GitHub release, run `t3code-customize --publish OWNER/REPO` once (it is remembered, and `--publish off` stops it). After each build the tool uploads the zip as release `v<version>` and deletes all but the two newest releases of that form, so the current and the previous one stay. It uses the GitHub CLI (`gh`) logged in as the owner of the repo, and a failed upload is logged and never fails the build.

## How it differs from the Linux tool

The Windows build ships the desktop code in `resources\app.asar` and the server and web client in `resources\server.asar`, so the overlay rebuilds both. The tool copies the whole install folder, replaces the two asars in the copy and runs that copy; the installed app is only read. The Electron asar integrity fuse is off in T3 Code builds, which is why this works. There is no native helper to reuse (it is Linux-only upstream), and the build is found through `state.json` instead of a symlink.

## Taking upstream's patch updates

`origin` is this repo and `upstream` is btsouth's. Before every build the tool fetches `upstream/main`. A plain clone fast-forwards to all of it. This copy has commits of its own (the Windows script and docs), so it takes only upstream's `patches/` and `checks.json`: his newer ports replace the ones here, patches he dropped or renamed are removed here too, and the patches only this repo has stay. The merge is recorded with this side's other files kept, so the copy counts as up to date and an upstream edit to `t3code-customize`, `AGENTS.md` or the docs can never block a rebuild. Those upstream changes are not applied automatically; take one by hand with `git checkout upstream/main -- <file>`. If taking the patches fails, the log says why (`git status` in the repo shows the rest).
