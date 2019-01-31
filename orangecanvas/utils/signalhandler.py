"""
Process Signal Handler
----------------------

Install a handler for OS process's SIGINT and SIGHUP signals (:mod:`signal`).


See Also
--------
signal

"""
import os
import signal
import threading

from AnyQt.QtCore import QObject, QSocketNotifier, QTimer, QCoreApplication
from AnyQt.QtCore import Signal, Slot


class SignalNotifier(QObject):
    """
    Example
    -------
    >>> app = QCoreApplication.instance() or QCoreApplication([])
    >>> handler = SignalNotifier.instance()
    >>> handler.install()
    >>> _ = handler.sigint.connect(
    ...     lambda: print("Received SIGINT") or app.exit(42)
    ... )
    >>> QTimer.singleShot(0, lambda: os.kill(os.getpid(), signal.SIGINT))
    >>> app.exec()  # << ctrl + c
    Received SIGINT
    42

    Note
    ----
    On windows console control events CTRL_BREAK_EVENT and CTRL_C_EVENT are
    interpreted as SIGINT and `sigint` signal is emitted for them.
    """
    #: Signal emitted on SIGINT
    sigint = Signal()
    #: Signal emitted on SIGHUP
    sighup = Signal()

    def __init__(self):
        raise TypeError(
            "`SignalNotifier` is a singleton and cannot be instantiated. "
            "`Use SignalNotifer.instance()` instead"
        )
    #: The singleton instance
    __instance = None  # type: SignalNotifier
    __lock = threading.Lock()
    __pollTimer = None  # type: QTimer
    __notifier = None   # type: QSocketNotifier

    @classmethod
    def instance(cls):
        # type: () -> SignalNotifier
        """
        Return the single instance of the SignalNotifier class.

        Returns
        -------
        instance: SignalNotifier
        """
        with cls.__lock:
            if cls.__instance is None:
                cls.__instance = SignalNotifier.__new__(SignalNotifier)
                super(SignalNotifier, cls.__instance).__init__()
        return cls.__instance

    @Slot()
    def __read_wakeup_fd(self):
        self.__notifier.setEnabled(False)
        try:
            try:
                # need to read all
                sig = os.read(self.__fd[0], 1)
            except BlockingIOError:
                return
            except OSError:
                ...
            else:
                sig = sig[0]
                if sig == signal.SIGINT:
                    self.sigint.emit()
                else:
                    self.sighup.emit()
        finally:
            self.__notifier.setEnabled(True)

    def _install_wakeup_fd(self):
        fdread, fdwrite = _mk_pipe()
        self.__fd = fdread, fdwrite
        self.__notifier = notifier = QSocketNotifier(
            fdread, QSocketNotifier.Read, self
        )
        notifier.activated.connect(self.__read_wakeup_fd)
        signal.set_wakeup_fd(fdwrite)
        def handler(sig, _):
            pass
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGHUP, handler)

    @Slot()
    def __nop(self):
        pass

    def _install_poll(self):
        # timer with a 'nop' slot, Qt event loop must give the cpython
        # interpreter loop a chance to actually handle the signal (see `signal`
        # doc)
        self.__pollTimer = QTimer(self, interval=1000)
        self.__pollTimer.timeout.connect(self.__nop)
        self.__pollTimer.start()

        def handler(sig, _):
            # type: (int, ...) -> None
            if sig == signal.SIGINT:
                self.sigint.emit()
            elif sig == signal.SIGHUP:
                self.sighup.emit()
        signal.signal(signal.SIGINT, handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, handler)
        if os.name == "nt" and hasattr(signal, "SIGBREAK"):
            def handler(sig, _):
                if sig == signal.SIGBREAK:
                    self.sigint.emit()
            signal.signal(signal.SIGBREAK, handler)

    def install(self):
        """
        Install this instance as the signal handler for the SIGINT signal
        """
        if os.name == "posix" and hasattr(signal, "set_wakeup_fd"):
            self._install_wakeup_fd()
        else:
            self._install_poll()


def _mk_pipe():
    if hasattr(os, "pipe2"):
        fdread, fdwrite = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    else:
        import fcntl

        def setflags(fd, statusflags, fdflags):
            f = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, f | statusflags)
            f = fcntl.fcntl(fd, fcntl.F_GETFD)
            fcntl.fcntl(fd, fcntl.F_SETFD, f | fdflags)
        fdread, fdwrite = os.pipe()
        try:
            setflags(fdread, os.O_NONBLOCK, fcntl.FD_CLOEXEC)
            setflags(fdwrite, os.O_NONBLOCK, fcntl.FD_CLOEXEC)
        except BaseException:
            os.close(fdread)
            os.close(fdwrite)
            raise
    return fdread, fdwrite
