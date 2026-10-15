"""Shared pieces of the tests: the tool loaded as a module, a fake asar, and the scenario and check helpers."""
import importlib.machinery
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIGHTLY = 'T3 Code (TestNightly).exe'
REAL = {'T3 Code (Alpha).exe', 'T3 Code (Nightly).exe', 't3-resource-monitor.exe'}
assert NIGHTLY not in REAL


def load_customize():
    loader = importlib.machinery.SourceFileLoader('t3customize', str(HERE / 't3code-customize'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('t3customize', loader))
    loader.exec_module(module)
    return module


CUSTOMIZE = load_customize()

ASAR = '''
import json, struct
def make_asar(version):
    body = json.dumps({'version': version}).encode()
    encoded = json.dumps({'files': {'package.json': {'size': len(body), 'offset': '0'}}}, separators=(',', ':')).encode()
    padded = encoded + b'\\0' * ((-len(encoded)) % 4)
    header = struct.pack('<II', 4 + len(padded), len(encoded)) + padded
    return struct.pack('<II', 4, len(header)) + header + body
'''


def scenario(name):
    def wrap(function):
        def run():
            print(f'- {name} ... ', end='', flush=True)
            function()
            print('ok')
        run.__name__ = function.__name__
        return run
    return wrap


def check(condition, message):
    assert condition, message
