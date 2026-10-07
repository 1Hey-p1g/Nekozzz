"""Existing complete tests/ with the documented process-local GC isolation."""
import gc
import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gc.disable()
folder = Path(__file__).resolve().parents[1] / 'report/pruning'
folder.mkdir(parents=True, exist_ok=True)
name = sys.argv[1]
started = time.monotonic()
with (folder / (name + '_tests.log')).open('w', encoding='utf-8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
               status='PASS' if result.wasSuccessful() else 'FAIL', gc_disabled=True,
               seconds=round(time.monotonic() - started, 3))
(folder / (name + '_tests.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(summary)
sys.exit(not result.wasSuccessful())
