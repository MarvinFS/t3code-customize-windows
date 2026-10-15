# t3code-customize on Windows

Windows port of [btsouth/t3code-customize](https://github.com/btsouth/t3code-customize). It puts your 5 hour and weekly usage, context and tokens per second under the T3 Code composer. Patches 0001 to 0003 come from btsouth and are ported here when a nightly moves the code they touch; 0004 and 0005 exist only in this repo (see the table in `.github/README.md`). Only `t3code-customize` knows about Windows. The repo root `README.md` is btsouth's Linux one, left unchanged so his updates merge cleanly; what it says about the patches and the build still holds, except that it counts three patches and this repo has five.

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

Before a build the tool applies the patches to the nightly's exact upstream commit and runs, all at once, the test files and package typechecks listed in `checks.json`: `vp test run` over 17 test files, and `tsc-rs --noEmit -p <package>/tsconfig.json` over 8 packages. `tsc-rs` is Theo Browne's Rust port of the TypeScript 7 compiler (the `tsc-rs` package, which T3 Code already depends on and calls from its own `typecheck` scripts). The tool used to run the official `tsc` 7.0.2 and switched on 2026-10-15.

Measured that day on this PC, the 8 typechecks together took 24 to 26 seconds with `tsc` and 10 seconds with `tsc-rs`, with 0 errors from both. An injected type error was caught by both with the same message, and only the exit code differs (1 against 2). `tsc-rs` also prints Effect language-service suggestions into the log, about 150 lines for `apps/server`; they do not fail the build. The test step takes longer than either compiler, so a build is not 15 seconds faster. `tsc-rs` reports itself as 7.1.0-dev, so if it ever fails a build that `tsc` passes, change `tsc-rs` back to `tsc` in `checks()` in `t3code-customize`.

`checks.windows.json` lists tests that fail on Windows for a reason that is not a patch regression, each with its reason, and a build continues when only those fail. Any other failure stops it. Today that is the two permission-bit assertions added by patch 0002, one upstream test that looks for the Unix path `/synthetic/project`, and the upstream steer test "moves the root's foreground subagents to the background before a steer (never answers)", which also fails on unpatched upstream here.

## Keeping it current

`schedule` registers the task `t3code-customize`. It runs at sign-in and every hour, without a window. Each run fetches upstream's latest patches, compares the installed `app.asar` and `server.asar` with the last build, and does nothing when neither changed. When T3 Code updates itself, the next run rebuilds and shows a notification. Until then the shortcut opens stock T3 Code and says why.

T3 Code downloads an update well before it installs it (the tray's "restart to install"). When a run finds such a download, it unpacks the app from it with 7-Zip and builds for that version ahead, leaving the installed app alone, and notifies you. Once that version is installed, by the tray or by an install request (below), the next run takes the build made ahead instead of building again, after checking that the installed `app.asar` and `server.asar` are byte for byte the ones it built from.

T3 can also be updated on request. When a file named `install-update` exists in `%LOCALAPPDATA%	3code-customize` and is less than 10 minutes old, the next run quits T3 Code, checks the download against the sha512 T3 recorded, installs it silently with the flags T3's updater uses, takes or makes the build, and opens "T3 Code (Customized)" again. Create the file and run `Start-ScheduledTask t3code-customize` to ask. The work happens in the task, so it survives T3 closing even when you start it from T3's own terminal.

If a nightly breaks the patches the run stops, tells you once, and waits 6 hours (or until upstream ships new patches) before trying again. Your installed T3 Code is never touched. The progress of unattended runs is in `%LOCALAPPDATA%\t3code-customize\cache\unattended.log`.

Commands: `t3code-customize` (build now), `status`, `off`, `on`, `pack`, `schedule`, `unschedule`, `uninstall`, `launch`. `--install-dir` points at a T3 Code folder when it is not under `%LOCALAPPDATA%\Programs`. `pack` zips the two patched asars of the current build into `%LOCALAPPDATA%\t3code-customize\packs` for installing by hand (see "Install without building" in `.github/README.md`). Old builds are pruned after each build, keeping the current one, the one made ahead and the one before the current; `pack` keeps the current and the previous zip. To publish every build as a GitHub release, run `t3code-customize --publish OWNER/REPO` once (it is remembered, and `--publish off` stops it). After each build the tool uploads the zip as release `v<version>` and deletes all but the two newest releases of that form, so the current and the previous one stay. It uses the GitHub CLI (`gh`) logged in as the owner of the repo, and a failed upload is logged and never fails the build.

## How it differs from the Linux tool

The Windows build ships the desktop code in `resources\app.asar` and the server and web client in `resources\server.asar`, so the overlay rebuilds both. The tool copies the whole install folder, replaces the two asars in the copy and runs that copy; the installed app is only read. The Electron asar integrity fuse is off in T3 Code builds, which is why this works. There is no native helper to reuse (it is Linux-only upstream), and the build is found through `state.json` instead of a symlink.

## Taking upstream's patch updates

`origin` is this private repo and `upstream` is btsouth's. The tool merges `upstream/main` before every build. A conflict with a local edit aborts the merge, reports it, and leaves the repo as it was; resolve it with `git merge upstream/main` by hand.
