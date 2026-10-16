#!/usr/bin/env python3
"""Tests for guards the tool must not lose: the rebuilt app keeps T3 Connect's public config, a stale or switched-off build
falls back to stock T3 Code, the Start Menu shortcut gets its values as variables, a second run cannot take the build lock, and publishing marks the
newest nightly as Latest without deleting the build it just uploaded.
Fake apps in a temp folder, never the real install or state. Windows only.

  python test_guards.py
"""
from contextlib import contextmanager
import json
import msvcrt
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from testkit import CUSTOMIZE as c, NIGHTLY, check, scenario

RELAY = 'https://relay.example.test'


@contextmanager
def workdir():
    folder = Path(tempfile.mkdtemp(prefix='t3guards-test-'))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@contextmanager
def patched(**names):
    saved = {name: getattr(c, name) for name in names}
    for name, value in names.items():
        setattr(c, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(c, name, value)


def write_asar(path, files):
    """An asar holding {'folder/file.js': bytes}, in the layout Archive reads."""
    tree, body = {'files': {}}, b''
    for key, data in files.items():
        *folders, name = key.split('/')
        node = tree
        for folder in folders:
            node = node['files'].setdefault(folder, {'files': {}})
        node['files'][name] = {'size': len(data), 'offset': str(len(body))}
        body += data
    encoded = json.dumps(tree, separators=(',', ':')).encode()
    padded = encoded + b'\0' * ((-len(encoded)) % 4)
    header = struct.pack('<II', 4 + len(padded), len(encoded)) + padded
    path.write_bytes(struct.pack('<II', 4, len(header)) + header + body)


def overlay_with(folder, built_main):
    """overlay() over a fake stock app.asar that carries the relay URL, with a fake build whose main.cjs is built_main."""
    stock = folder / 'app.asar'
    write_asar(stock, {'package.json': b'{}', 'apps/desktop/dist-electron/main.cjs': RELAY.encode()})
    main = folder / 'build/apps/desktop/dist-electron/main.cjs'
    main.parent.mkdir(parents=True)
    main.write_bytes(built_main)
    c.overlay(stock, folder / 'out.asar', folder / 'build', {'T3CODE_RELAY_URL': RELAY})


@scenario("refuses a rebuilt app that lost T3 Connect's public config, and accepts one that kept it")
def overlay_keeps_config():
    with workdir() as folder:
        overlay_with(folder, b'statsForNerds ' + RELAY.encode())
    with workdir() as folder:
        try:
            overlay_with(folder, b'statsForNerds')
        except c.Stop as stop:
            check('T3CODE_RELAY_URL' in str(stop), f'refused for another reason: {stop}')
        else:
            check(False, 'an overlay without the public config was accepted')


def fake_install(folder, name):
    """A folder shaped like an installed T3 Code (or a finished build): both asars and a Nightly exe."""
    root = folder / name
    (root / 'resources').mkdir(parents=True)
    for asar in c.LAYOUT:
        (root / 'resources' / asar).write_bytes(b'stock ' + asar.encode())
    (root / NIGHTLY).write_bytes(b'')
    return root


@scenario('opens the customized build only while it matches the installed T3 Code, else stock')
def launch_falls_back():
    with workdir() as folder:
        install, build = fake_install(folder, 'install'), fake_install(folder, 'build')
        state, disabled = folder / 'state.json', folder / 'disabled'
        with patched(find_stock=lambda explicit=None: install, STATE=state, DISABLED=disabled):
            check(c.launch_target() == (install, None), 'no build recorded: expected stock')
            state.write_text(json.dumps({'build': str(build), 'stock': c.fingerprint(install)}))
            target, notice = c.launch_target()
            check(target == c.stock_exe(build).resolve() and notice is None, f'matching build: {target}, {notice}')
            disabled.touch()
            check(c.launch_target() == (install, None), 'switched off: expected stock')
            disabled.unlink()
            (install / 'resources/app.asar').write_bytes(b'replaced by a T3 Code update')
            target, notice = c.launch_target()
            check(target == install and notice and 'updated' in notice, f'stale build: {target}, {notice}')


AWKWARD = "repo'with;quotes $(1+1) `tick"  # legal in a Windows folder name, and fatal if pasted into a PowerShell script


@scenario('hands the shortcut its paths as variables; the PowerShell script text never contains one')
def shortcut_is_not_interpolated():
    calls = []

    def record(script, **values):
        calls.append((script, values))
        return SimpleNamespace(returncode=0, stderr='')

    with workdir() as folder:
        install = fake_install(folder, 'install')
        for name in ('plain', AWKWARD):
            with patched(powershell=record, REPO=folder / name, BIN=folder / 'bin/t3.cmd', DESKTOP=folder / 'menu/app.lnk'):
                c.install_launcher_windows(install)
        (plain_script, _), (awkward_script, awkward) = calls
        check(plain_script == awkward_script, 'the script text depends on the repo path')
        check(AWKWARD not in awkward_script, 'the repo path was pasted into the script')
        check(AWKWARD in awkward['args'] and awkward['dir'] == folder / AWKWARD, f'values not passed as variables: {awkward}')


@scenario('makes a working shortcut from a path full of quotes and semicolons (real PowerShell, read back through COM)')
def shortcut_round_trip():
    with workdir() as folder:
        install, repo, lnk = fake_install(folder, 'install'), folder / AWKWARD, folder / 'menu/app.lnk'
        with patched(REPO=repo, BIN=folder / 'bin/t3.cmd', DESKTOP=lnk):
            c.install_launcher_windows(install)
        back = c.powershell('$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:T3C_LNK); '
                            '[Console]::Out.Write($s.Arguments + "|" + $s.WorkingDirectory)', lnk=lnk)
        check(back.returncode == 0 and back.stdout == f'"{repo / c.NAME}" launch|{repo}', f'{back.stdout!r} {back.stderr}')


@scenario('refuses a second run while one holds the build lock, and runs again once it is released')
def second_run_refused():
    with workdir() as folder:
        cache = folder / c.NAME / 'cache'
        cache.mkdir(parents=True)

        def second_run():  # the real command line, on a state folder of its own; it stops at the missing install, after the lock
            return subprocess.run([sys.executable, str(c.REPO / c.NAME), 'build', '--no-pull', '--install-dir', str(folder / 'missing')],
                                  env={**os.environ, 'LOCALAPPDATA': str(folder)}, capture_output=True, text=True, timeout=120)

        with (cache / 'lock').open('w') as holder:
            msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
            refused = second_run()
            msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
        check(refused.returncode == 1 and 'already running' in refused.stderr, f'locked: {refused.returncode} {refused.stderr!r}')
        free = second_run()
        check('already running' not in free.stderr and 'No T3 Code install' in free.stderr, f'released: {free.returncode} {free.stderr!r}')


def publish_with(existing, version):
    """Run the real publish() against a fake gh whose repo holds the existing tags; return the gh calls it made."""
    calls = []

    def fake_run(args, **_):
        calls.append(args[1:])
        listed = json.dumps([{'tagName': tag} for tag in existing]) if args[1:3] == ['release', 'list'] else ''
        return SimpleNamespace(returncode=0, stdout=listed, stderr='')

    with patched(subprocess=SimpleNamespace(run=fake_run), shutil=SimpleNamespace(which=lambda name: 'gh'),
                 make_pack=lambda *args: Path('pack.zip'), sha256=lambda path: '0' * 64, say=lambda *args: None):
        check(c.publish(Path('build'), version, 'a' * 40, 'owner/repo'), 'publish reported a failure')
    return calls


@scenario('marks the newest nightly Latest and keeps the build it just published, even an older one')
def publish_orders_by_nightly():
    newest, middle, older = 'v0.1.1-nightly.20261016.3190', 'v0.0.46-nightly.20261015.3171', 'v0.0.46-nightly.20261015.3158'
    # GitHub lists by its createdAt, the tagged commit's date, so the order here says nothing about which build is newer.
    calls = publish_with([older, newest, middle, 'v1.0'], older.lstrip('v'))
    deleted = [call[2] for call in calls if call[:2] == ['release', 'delete']]
    latest = [call[2] for call in calls if call[:2] == ['release', 'edit'] and '--latest' in call]
    check(deleted == [middle], f'deleted {deleted}')
    check(latest == [newest], f'marked Latest {latest}')


if __name__ == '__main__':
    for test in (overlay_keeps_config, launch_falls_back, shortcut_is_not_interpolated, shortcut_round_trip, second_run_refused,
                 publish_orders_by_nightly):
        test()
    print('all passed')
