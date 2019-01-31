import unittest

import os
import signal

from AnyQt.QtCore import QCoreApplication, QTimer
from AnyQt.QtTest import QSignalSpy

from ...gui.test import QCoreAppTestCase
from ..signalhandler import SignalNotifier


class TestSignalHandler(QCoreAppTestCase):
    @unittest.skipIf(lambda: os.name == "nt", "")
    def test_sighandler(self):
        app = QCoreApplication.instance()
        handler = SignalNotifier.instance()
        handler.install()
        spy = QSignalSpy(handler.sigint)
        handler.sigint.connect(
            lambda: app.exit(42)
        )
        QTimer.singleShot(0, lambda: os.kill(os.getpid(), signal.SIGINT))
        self.assertTrue(len(spy) or spy.wait())
        self.assertEqual(list(spy), [[]])
