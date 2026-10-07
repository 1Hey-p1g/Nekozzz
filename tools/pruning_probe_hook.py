"""Candidate diagnostic hook only. Never installed in the formal spec.

The external probe runs after the real entry point has built/shown its window.
With no probe environment variable, the candidate follows the normal event loop.
"""
import os
if os.environ.get('NEKOZZZ_PRUNE_PROBE'):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    _original_exec = QApplication.exec

    def _diagnostic_exec(*args):
        def run():
            import runpy
            runpy.run_path(os.environ['NEKOZZZ_PRUNE_PROBE'], run_name='__main__')
        QTimer.singleShot(500, run)
        return _original_exec()

    QApplication.exec = _diagnostic_exec
