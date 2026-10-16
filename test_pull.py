#!/usr/bin/env python3
"""Tests for pull_latest(): a copy with commits of its own follows upstream's patches without ever conflicting on its script,
a plain clone still fast-forwards to everything, and a failure names its cause. Real git repos in a temp folder; the
tool's re-run of itself is intercepted. Windows only.

  python test_pull.py
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from test_guards import patched
from testkit import CUSTOMIZE as c, check, scenario

real_run = subprocess.run


def git(cwd, *args):
    return real_run(['git', *args], cwd=cwd, env={**os.environ, **c.GIT_ENV}, check=True, capture_output=True,
                    text=True, encoding='utf-8').stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


def commit(cwd, message):
    git(cwd, 'add', '-A')
    git(cwd, 'commit', '-q', '-m', message)


class Repos:
    """An upstream repo (script, patches, docs) and the clones of it that the tool runs in."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='t3pull-test-'))
        self.up = self.dir / 'up'
        self.up.mkdir()
        git(self.up, 'init', '-q', '-b', 'main')
        write(self.up / c.NAME, 'SCRIPT = base\n')
        write(self.up / 'patches/base.txt', 'base-1\n')
        write(self.up / 'patches/0001-a.patch', 'patch a v1\n')
        write(self.up / 'patches/0002-b.patch', 'patch b v1\n')
        write(self.up / 'checks.json', '{"tests": ["one"]}\n')
        write(self.up / 'README.md', 'readme v1\n')
        commit(self.up, 'v1')

    def clone(self, name, follows_upstream_remote):
        path = self.dir / name
        git(self.dir, 'clone', '-q', str(self.up), str(path))
        if follows_upstream_remote:  # a private copy: its own origin, btsouth's repo as 'upstream'
            git(path, 'remote', 'add', 'upstream', str(self.up))
            git(path, 'fetch', '-q', 'upstream')
        return path

    def own_commit(self, path):
        write(path / c.NAME, 'SCRIPT = ours\n')
        write(path / 'patches/0101-ours.patch', 'our patch\n')
        write(path / 'README.md', 'readme ours\n')
        commit(path, 'our own work')

    def upstream_moves(self):
        """What the maintainer does: edits the same script line, ports a patch again, renames another, adds a check."""
        write(self.up / c.NAME, 'SCRIPT = theirs\n')
        write(self.up / 'patches/base.txt', 'base-2\n')
        write(self.up / 'patches/0001-a.patch', 'patch a v2\n')
        git(self.up, 'mv', 'patches/0002-b.patch', 'patches/0002-renamed.patch')
        write(self.up / 'checks.json', '{"tests": ["one", "two"]}\n')
        write(self.up / 'README.md', 'readme v2\n')
        commit(self.up, 'v2')

    def close(self):  # git marks its object files read-only, which blocks rmtree on Windows
        shutil.rmtree(self.dir, onexc=lambda function, path, error: (os.chmod(path, 0o700), function(path)))


def pull(path, world):
    """pull_latest() in that checkout, with the lock and the tool's re-run of itself faked; returns how many times it re-ran."""
    runs = []

    def run(args, *rest, **options):
        if isinstance(args, list) and args[0] == sys.executable:
            runs.append(args)
            return SimpleNamespace(returncode=0)
        return real_run(args, *rest, **options)

    with patched(REPO=path, DATA=world.dir / 'data', LOCK=SimpleNamespace(fileno=lambda: 0),
                 msvcrt=SimpleNamespace(locking=lambda *args: None, LK_UNLCK=0)):
        c.subprocess.run = run
        try:
            c.pull_latest()
        except SystemExit as done:
            check(done.code == 0, f'the re-run was reported as exit {done.code}')
        finally:
            c.subprocess.run = real_run
    return len(runs)


@scenario("a copy with its own commits follows upstream's patches, even when upstream edited the same script line")
def copy_follows_patches():
    world = Repos()
    try:
        fork = world.clone('fork', follows_upstream_remote=True)
        world.own_commit(fork)
        world.upstream_moves()
        check(pull(fork, world) == 1, 'did not re-run the tool after taking new patches')

        def read(name):
            return (fork / name).read_text(encoding='utf-8')
        check(read(c.NAME) == 'SCRIPT = ours\n' and read('README.md') == 'readme ours\n', 'its own script or docs were replaced')
        check(read('patches/0001-a.patch') == 'patch a v2\n' and read('patches/base.txt') == 'base-2\n', 'patches not updated')
        check(not (fork / 'patches/0002-b.patch').exists() and (fork / 'patches/0002-renamed.patch').exists(),
              'a patch upstream renamed was kept under its old name or lost')
        check((fork / 'patches/0101-ours.patch').exists(), 'its own patch was removed')
        check(read('checks.json') == '{"tests": ["one", "two"]}\n', 'checks.json not updated')
        check(git(fork, 'rev-list', '--count', 'HEAD..upstream/main') == '0', 'still counts as behind upstream')
        check(git(fork, 'status', '--porcelain') == '', 'left the tree dirty')
        check(pull(fork, world) == 0, 'ran again with nothing new')
    finally:
        world.close()


@scenario('a plain clone still fast-forwards to everything upstream changed, script included')
def plain_clone_fast_forwards():
    world = Repos()
    try:
        plain = world.clone('plain', follows_upstream_remote=False)
        world.upstream_moves()
        check(pull(plain, world) == 1, 'did not re-run the tool after updating')
        check((plain / c.NAME).read_text(encoding='utf-8') == 'SCRIPT = theirs\n', 'the script was not updated')
        check((plain / 'README.md').read_text(encoding='utf-8') == 'readme v2\n', 'the docs were not updated')
    finally:
        world.close()


@scenario("saves an unfinished local port of the patches to a backup before taking upstream's")
def local_port_backed_up():
    world = Repos()
    try:
        fork = world.clone('fork', follows_upstream_remote=True)
        world.own_commit(fork)
        write(fork / 'patches/0001-a.patch', 'my unfinished port\n')  # not committed
        world.upstream_moves()
        pull(fork, world)
        backups = list((world.dir / 'data').glob('patches.bak-*'))
        check(len(backups) == 1 and (backups[0] / '0001-a.patch').read_text(encoding='utf-8') == 'my unfinished port\n', backups)
        check((fork / 'patches/0001-a.patch').read_text(encoding='utf-8') == 'patch a v2\n', "upstream's patch was not taken after the backup")
    finally:
        world.close()


@scenario('says why when upstream cannot be followed, instead of a generic conflict message')
def failure_names_its_cause():
    world = Repos()
    try:
        fork = world.clone('fork', follows_upstream_remote=False)
        world.own_commit(fork)
        stranger = world.dir / 'stranger'  # a repo with no history in common
        stranger.mkdir()
        git(stranger, 'init', '-q', '-b', 'main')
        write(stranger / 'patches/0001-x.patch', 'x\n')
        commit(stranger, 'unrelated')
        git(fork, 'remote', 'add', 'upstream', str(stranger))
        try:
            pull(fork, world)
        except c.Stop as stop:
            check('share no history' in str(stop), f'the message does not say why: {stop}')
        else:
            check(False, 'no stop for a repo with nothing in common')
    finally:
        world.close()


if __name__ == '__main__':
    for test in (copy_follows_patches, plain_clone_fast_forwards, local_port_backed_up, failure_names_its_cause):
        test()
    print('all passed')
