#!/usr/bin/env python3
"""Tests for installing T3's downloaded update on request and adopting a build made ahead for it, against a fake install,
updater cache and state folder. It never touches the
real app: the fake exe name cannot match it and the installer call is intercepted.

  python test_install_pending.py
"""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from testkit import ASAR, CUSTOMIZE as c, NIGHTLY, REAL, check, scenario

exec(ASAR, ns := {})
make_asar = ns['make_asar']
OLD, NEW = '0.0.46-nightly.20261014.3093', '0.0.46-nightly.20261014.3105'
real_run = subprocess.run


class World:
    def __init__(self, pending=NEW, checksum=True, installs=NEW):
        self.dir = Path(tempfile.mkdtemp(prefix='t3pending-test-'))
        self.install = self.dir / 'install'
        (self.install / 'resources').mkdir(parents=True)
        shutil.copy2(sys.executable, self.install / NIGHTLY)
        (self.install / 'resources/app.asar').write_bytes(make_asar(OLD))
        c.PENDING = self.dir / 'pending'
        c.STATE, c.PREBUILT = self.dir / 'state.json', self.dir / 'prebuilt.json'
        c.fetch_nightly = lambda newest: None  # these cover T3's own download; GitHub is faked in its own tests
        c.PENDING.mkdir()
        self.installer = c.PENDING / f'T3-Code-{pending}-x64.exe'
        self.installer.write_bytes(b'fake installer ' + pending.encode())
        digest = base64.b64encode(hashlib.sha512(self.installer.read_bytes()).digest()).decode()
        (c.PENDING / 'update-info.json').write_text(json.dumps(
            {'fileName': self.installer.name, 'sha512': digest if checksum else 'x' + digest[1:], 'isAdminRightsRequired': False}))
        self.ran, self.installs = [], installs
        self.app = subprocess.Popen([str(self.install / NIGHTLY), '-c', 'import time; time.sleep(120)'])
        assert c.running(NIGHTLY)

    def fake_run(self, args, *rest, **kwargs):
        if args[0] == str(self.installer):
            self.ran.append(args[1:])
            check(self.app.poll() is not None, 'T3 was still running when the installer started')
            (self.install / 'resources/app.asar').write_bytes(make_asar(self.installs))
            return subprocess.CompletedProcess(args, 0)
        check(not REAL & set(args), f'touched the real app: {args}')
        return real_run(args, *rest, **kwargs)

    def install_pending(self):
        subprocess.run = self.fake_run
        try:
            c.install_pending(self.install)
        finally:
            subprocess.run = real_run

    def close(self):
        self.app.kill()
        self.app.wait()
        shutil.rmtree(self.dir, ignore_errors=True)


def stops(world):
    try:
        world.install_pending()
    except c.Stop as stop:
        return str(stop)
    return None


@scenario('quits T3, installs the newer download silently, without --force-run')
def installs():
    w = World()
    try:
        w.install_pending()
        check(w.ran == [['--updated', '/S']], w.ran)
        check(c.installed_version(w.install) == NEW, 'version')
    finally:
        w.close()


@scenario('leaves T3 running when the download is not newer')
def same_version():
    w = World(pending=OLD)
    try:
        w.install_pending()
        check(not w.ran and w.app.poll() is None, 'installed or quit anyway')
    finally:
        w.close()


@scenario('refuses a download whose checksum does not match, before quitting T3')
def bad_checksum():
    w = World(checksum=False)
    try:
        check('checksum' in (stops(w) or ''), 'did not stop')
        check(not w.ran and w.app.poll() is None, 'installed or quit anyway')
    finally:
        w.close()


@scenario('reports an installer that did not change the version')
def no_change():
    w = World(installs=OLD)
    try:
        check('installed version is ' + OLD in (stops(w) or ''), 'did not stop')
    finally:
        w.close()


@scenario('does nothing without a download')
def nothing_pending():
    w = World()
    try:
        shutil.rmtree(c.PENDING)
        w.install_pending()
        check(not w.ran and w.app.poll() is None, 'installed or quit anyway')
    finally:
        w.close()


def prebuilt(w, version, asars):
    build = w.dir / 'builds' / version
    build.mkdir(parents=True)
    c.save(c.PREBUILT, {'stock': {}, 'version': version, 'recipe': 'r', 'build': str(build), 'asars': asars})
    return build


@scenario('adopts the build made ahead once its version is installed')
def adopts():
    w = World()
    try:
        (w.install / 'resources/server.asar').write_bytes(b'server')
        build = prebuilt(w, OLD, c.asar_hashes(w.install))
        c.adopt_prebuilt(w.install)
        state = c.load(c.STATE)
        check(state['build'] == str(build) and state['stock'] == c.fingerprint(w.install) and 'asars' not in state, state)
        check(not c.PREBUILT.exists(), 'prebuilt.json kept')
    finally:
        w.close()


@scenario('drops a build made ahead whose asars differ from what got installed')
def refuses_mismatch():
    w = World()
    try:
        (w.install / 'resources/server.asar').write_bytes(b'server')
        prebuilt(w, OLD, {'app.asar': 'x', 'server.asar': 'y'})
        c.adopt_prebuilt(w.install)
        check(not c.STATE.exists() and not c.PREBUILT.exists(), 'adopted or kept a mismatched build')
    finally:
        w.close()


@scenario('keeps a build made ahead for a version not installed yet')
def waits():
    w = World()
    try:
        prebuilt(w, NEW, {})
        c.adopt_prebuilt(w.install)
        check(not c.STATE.exists() and c.PREBUILT.exists(), 'adopted too early')
    finally:
        w.close()


@scenario("unpacks T3's real downloaded installer into an install-shaped folder")
def extracts():
    real = Path(c.LOCAL) / 't3code-updater/installer.exe'
    if not real.is_file():
        print('(no installer on this PC, skipped) ', end='')
        return
    out = Path(tempfile.mkdtemp(prefix='t3extract-test-'))
    try:
        c.extract_installer(real, out / 'app')
        check(list((out / 'app').glob('T3 Code*.exe')) and (out / 'app/resources/server.asar').is_file(), 'layout')
        check(not (out / 'installer').exists(), 'left the outer archive behind')
    finally:
        shutil.rmtree(out, ignore_errors=True)


@scenario('prunes by build time in the name, keeping the current build, the one before it and the one made ahead')
def prunes():
    d = Path(tempfile.mkdtemp(prefix='t3prune-test-'))
    try:
        c.DATA, c.STATE, c.PREBUILT = d, d / 'state.json', d / 'prebuilt.json'
        names = [f'v-r-2026101{i}-120000' for i in range(6)]
        for name in names:
            (d / 'builds' / name).mkdir(parents=True)
        left = lambda: sorted(p.name for p in (d / 'builds').iterdir())
        c.prune()  # no state.json yet: the newest build counts as the current one
        check(left() == names[4:], f'newest and the one before it: {left()}')
        for name in names[:4]:
            (d / 'builds' / name).mkdir()
        c.save(c.STATE, {'build': str(d / 'builds' / names[3])})
        c.save(c.PREBUILT, {'build': str(d / 'builds' / names[5])})
        c.prune()
        check(left() == [names[2], names[3], names[5]], f'previous, current and made ahead: {left()}')
    finally:
        shutil.rmtree(d, ignore_errors=True)


@scenario('packs the two asars of the current build and keeps only the current and the previous zip')
def packs():
    import zipfile
    d = Path(tempfile.mkdtemp(prefix='t3pack-test-'))
    try:
        c.STATE, c.PACKS = d / 'state.json', d / 'packs'
        try:
            c.cmd_pack(None)
            check(False, 'packed without a build')
        except c.Stop:
            pass
        for version in ['0.0.46-nightly.2026101%d.100' % n for n in range(3)]:
            build = d / 'builds' / version
            (build / 'resources').mkdir(parents=True)
            for name in c.LAYOUT:
                (build / 'resources' / name).write_bytes((version + name).encode() * 100)
            (build / 'resources' / 'other.bin').write_bytes(b'not packed')
            c.save(c.STATE, {'build': str(build), 'version': version, 'commit': 'abc123'})
            c.cmd_pack(None)
            check(c.PACKS.joinpath(f'{c.NAME}-{version}.zip').exists(), f'no zip for {version}')
        check(sorted(p.name for p in c.PACKS.glob('*.zip')) == [f'{c.NAME}-0.0.46-nightly.2026101{n}.100.zip' for n in (1, 2)],
              f'kept {[p.name for p in c.PACKS.glob("*.zip")]}')
        with zipfile.ZipFile(c.PACKS / f'{c.NAME}-{version}.zip') as z:
            check(sorted(z.namelist()) == ['resources/app.asar', 'resources/server.asar'], z.namelist())
            check(z.read('resources/app.asar') == (version + 'app.asar').encode() * 100, 'app.asar bytes differ')
            check(z.comment == f'{version} abc123'.encode(), z.comment)
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Gh:
    """Fakes the gh CLI for publish: records every call and answers the few it needs."""
    def __init__(self, releases, create_fails=False):
        self.releases, self.create_fails, self.calls = releases, create_fails, []

    def run(self, args, *rest, **kwargs):
        sub = ' '.join(args[1:3])
        self.calls.append((sub, args, kwargs.get('env', {}).get('GH_TOKEN')))
        code, out = 0, ''
        if sub == 'auth token':
            out = 'token-for-' + args[args.index('--user') + 1]
        elif sub == 'release view':
            code = 1  # the tag is new
        elif sub == 'release create' and self.create_fails:
            code = 1
        elif sub == 'release list':
            out = json.dumps(self.releases)
        return subprocess.CompletedProcess(args, code, out, 'boom' if code else '')

    def __enter__(self):
        self.saved = subprocess.run, c.shutil.which
        subprocess.run, c.shutil.which = self.run, lambda name, **kw: 'gh'
        return self

    def __exit__(self, *exc):
        subprocess.run, c.shutil.which = self.saved

    def names(self):
        return [call[0] for call in self.calls]


@scenario('publishes the zip as a release and keeps only the two newest of our releases')
def publishes():
    d = Path(tempfile.mkdtemp(prefix='t3publish-test-'))
    try:
        c.PACKS = d / 'packs'
        build = d / 'build'
        (build / 'resources').mkdir(parents=True)
        for name in c.LAYOUT:
            (build / 'resources' / name).write_bytes(name.encode() * 10)
        release = lambda tag, day: {'tagName': tag, 'createdAt': f'2026-10-{day}T00:00:00Z'}
        listed = [release('v0.0.46-nightly.20261013.1', 13), release('v0.0.46-nightly.20261015.3', 15),
                  release('v0.0.46-nightly.20261014.2', 14), release('notes-for-humans', 1)]
        with Gh(listed) as gh:
            check(c.publish(build, '0.0.46-nightly.20261015.3', 'abcdef1234567890', 'me/repo') is True, 'did not report success')
        create = next(call for call in gh.calls if call[0] == 'release create')
        check('v0.0.46-nightly.20261015.3' in create[1] and create[1][create[1].index('--repo') + 1] == 'me/repo', create[1])
        check(create[2] == 'token-for-me', f'used the token of the repo owner: {create[2]}')
        deleted = [call[1][3] for call in gh.calls if call[0] == 'release delete']
        check(deleted == ['v0.0.46-nightly.20261013.1'], f'deleted {deleted}')
        check('--cleanup-tag' in next(call[1] for call in gh.calls if call[0] == 'release delete'), 'left the tag behind')
        check(len(list(c.PACKS.glob('*.zip'))) == 1, 'zip missing')
        with Gh(listed, create_fails=True) as gh:
            check(c.publish(build, '0.0.46-nightly.20261016.4', 'abcdef1234567890', 'me/repo') is False, 'hid a failed upload')
        check('release delete' not in gh.names(), 'deleted releases after a failed upload')
    finally:
        shutil.rmtree(d, ignore_errors=True)


class GitHub:
    """Fakes the releases API, nightly.yml and the installer download for fetch_nightly."""
    def __init__(self, version, payload=b'installer bytes', checksum=None):
        self.name = f'T3-Code-{version}-x64.exe'
        self.payload, self.downloads = payload, 0
        digest = checksum or base64.b64encode(hashlib.sha512(payload).digest()).decode()
        asset = lambda name: {'name': name, 'browser_download_url': 'https://x/' + name, 'state': 'uploaded', 'size': 1}
        self.api = json.dumps([{'tag_name': 'v' + version, 'assets': [asset(self.name), asset('nightly.yml')]}]).encode()
        self.feed = f'files:\n  - url: {self.name}\n    sha512: {digest}\n'.encode()

    def urlopen(self, url, timeout=None):
        import io
        return io.BytesIO(self.feed if url.endswith('nightly.yml') else self.api)

    def urlretrieve(self, url, path):
        self.downloads += 1
        Path(path).write_bytes(self.payload)

    def __enter__(self):
        self.saved = urllib.request.urlopen, urllib.request.urlretrieve, c.DOWNLOADS
        urllib.request.urlopen, urllib.request.urlretrieve = self.urlopen, self.urlretrieve
        c.DOWNLOADS = Path(tempfile.mkdtemp(prefix='t3fetch-test-')) / 'downloads'
        return self

    def __exit__(self, *exc):
        shutil.rmtree(c.DOWNLOADS.parent, ignore_errors=True)
        urllib.request.urlopen, urllib.request.urlretrieve, c.DOWNLOADS = self.saved


@scenario('fetches a newer Nightly from GitHub once and checks it')
def fetches():
    with GitHub(NEW) as gh:
        found = c.fetch_nightly(OLD)
        check(found and found[1] == NEW and found[0].read_bytes() == gh.payload, found)
        check(c.fetch_nightly(OLD)[0] == found[0] and gh.downloads == 1, 'downloaded twice')


@scenario('ignores a GitHub Nightly that is not newer, and one whose checksum fails')
def fetch_refuses():
    with GitHub(OLD) as gh:
        check(c.fetch_nightly(OLD) is None and gh.downloads == 0, 'not newer')
    with GitHub(NEW, checksum='bad') as gh:
        check(c.fetch_nightly(OLD) is None and not list(c.DOWNLOADS.glob('*')), 'kept a bad download')


@scenario('is not interactive without a console (pythonw has no stdin), instead of crashing the unattended run')
def headless():
    folder = Path(tempfile.mkdtemp(prefix='t3headless-test-'))
    result = folder / 'result.txt'
    probe = folder / 'probe.py'
    # pythonw sets sys.stdin and sys.stdout to None, so print() cannot be used to report back.
    probe.write_text('\n'.join([
        'import importlib.machinery, importlib.util',
        f'loader = importlib.machinery.SourceFileLoader("t3c", {str(c.REPO / c.NAME)!r})',
        'module = importlib.util.module_from_spec(importlib.util.spec_from_loader("t3c", loader))',
        'loader.exec_module(module)',
        f'open({str(result)!r}, "w").write("%s %r" % (module.sys.stdin, module.interactive()))', '']))
    try:
        subprocess.run([str(Path(sys.executable).with_name('pythonw.exe')), '-I', str(probe)], check=True, timeout=60)
        check(result.read_text() == 'None False', f'stdin and interactive() under pythonw: {result.read_text()!r}')
    finally:
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    for test in (fetches, fetch_refuses, headless):
        test()
    for test in (same_version, bad_checksum, nothing_pending, adopts, refuses_mismatch, waits, extracts, prunes, packs,
                 publishes, no_change, installs):
        test()
    print('all passed')
