# T3 Code Stats Bar

Your 5 hour and weekly usage, context and tokens per second, right under the T3 Code composer.

Unofficial. Not affiliated with T3 Tools. Linux AppImage only for now.

## What you get

- **Usage meters** for the 5 hour and weekly limits, read from the limits T3 already fetches from your providers.
- **Context** used in the current thread. Hover it for the window, the automatic compaction threshold, and a Compact now button.
- **Tokens per second** for the last response, with turn time and token details on hover. Claude rates are observed from the stream; Codex rates are labeled approximate.
- **Cache rate** for the last turn.

Toggle it under Settings, Stats for Nerds.

## How it works

T3 Code is open source (MIT). This repo holds a few patches and one script. The script:

1. finds your installed T3 Code AppImage and reads the exact upstream commit it was built from,
2. applies the patches to that commit in a local checkout,
3. runs the patch tests, then rebuilds the web, server and desktop bundles,
4. lays them over a copy of your app, leaving the native parts untouched.

Everything runs on your machine. Your AppImage and your T3 data are never modified, and stock T3 Code is one command away.

## Install

You need Linux, git, Node 24+ and about 3 GB of disk for the source and dependencies.

```sh
git clone https://github.com/btsouth/t3code-stats-bar
cd t3code-stats-bar
./t3code-stats-bar install
```

The first build takes a few minutes. Then quit T3 Code fully and open **T3 Code (Stats Bar)** from your launcher.

If your AppImage isn't in `~/Applications` or `~/Downloads`, pass it once: `./t3code-stats-bar install --appimage /path/to/T3-Code.AppImage`.

## After T3 Code updates

```sh
t3code-stats-bar update
```

That pulls the latest patches and rebuilds for your new version. Until you do, the launcher opens stock T3 Code and tells you why.

## When a nightly breaks the patches

Upstream moves fast, so this happens often. You have three options:

- Point your coding agent at this repo and ask it to follow [AGENTS.md](AGENTS.md).
- Run it unattended: `t3code-stats-bar build --fix codex` (or `--fix claude`). This runs the agent with full permissions in the source checkout.
- Wait for this repo to catch up, then `t3code-stats-bar update`.

Your stock T3 Code keeps working in the meantime.

## Commands

```
t3code-stats-bar install     add the command and launcher, then build
t3code-stats-bar update      pull the latest patches, then build
t3code-stats-bar build       build for the installed AppImage
t3code-stats-bar launch      open the stats bar build if it matches, else stock
t3code-stats-bar status      show what the next launch will run
t3code-stats-bar off | on    switch between stock and the stats bar build
t3code-stats-bar uninstall   remove the launcher, builds and caches
```

## Good to know

- **Bugs:** before reporting anything to T3 Code, run `t3code-stats-bar off`, reopen and check it still happens on stock. Report stats bar problems here, not upstream.
- **T3 Connect:** upstream bakes its cloud config into official builds, and this repo doesn't ship it. Sign in and remote access may not work in the stats bar build. If you need them, put the `T3CODE_*` values in `~/.config/t3code-stats-bar/build.env` and rebuild with `--force`.
- **Other platforms:** macOS and Windows aren't supported. The patches are platform independent, so an agent can adapt the packaging steps.
- **Files:** builds live in `~/.local/share/t3code-stats-bar`, the source checkout and logs in `~/.cache/t3code-stats-bar`.

## License

MIT, same as T3 Code.
