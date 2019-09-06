import os
import time
import errno

from typing import Callable, TypeVar, AnyStr, IO

try:
    import fcntl
except ImportError:
    fcntl = None
    try:
        import msvcrt
        import win32file, win32api, winerror, pywintypes
    except ImportError:
        win32file = None


T = TypeVar("T")


def retry_timeout(
        func: 'Callable[[], T]',
        errors=(OSError,),
        timeout=0.,
) -> T:
    if timeout == 0:
        return func()
    start = time.perf_counter()
    while timeout > 0:
        try:
            return func()
        except errors:
            pass

        time.sleep(1e-4)
        now = time.perf_counter()
        timeout -= (now - start)
        start = now
    raise TimeoutError()

# Notes:
# *  `open(..., mode="a", opener=...)`
# * will seek to end for 'a' mode after opener returns
# * will add O_CLOEXC or O_NOINHERIT to flags for opener


def open_locked_posix(path, mode="r", timeout=0., **kwargs) -> IO:
    """
    open_locked implementation using flock after open, posix conformant.
    """
    def opener(path: AnyStr, flags: int) -> int:
        if flags & (os.O_RDWR | os.O_WRONLY):
            lock = fcntl.LOCK_EX
        else:
            lock = fcntl.LOCK_SH

        # trunc only after the lock is acquired
        fd = os.open(path, flags ^ (flags & os.O_TRUNC))
        try:
            if timeout >= 0:
                retry_timeout(
                    lambda: fcntl.flock(fd, lock | fcntl.LOCK_NB),
                    timeout=timeout,
                )
            else:
                fcntl.flock(fd, lock)
            if flags & os.O_TRUNC:
                os.ftruncate(fd, 0)
        except BaseException:
            os.close(fd)
            raise
        return fd
    return open(path, mode, opener=opener, **kwargs)


def open_locked_bsd(path, mode="r", timeout=0., **kwargs) -> IO:
    """
    open_locked implementation using open with O_(EX|SH)LOCK bsd flags.
    """
    def opener(path: AnyStr, flags: int) -> int:
        if flags & (os.O_RDWR | os.O_WRONLY):
            lock = os.O_EXLOCK
        else:
            lock = os.O_SHLOCK

        if timeout >= 0:
            block = flags & os.O_NONBLOCK
            fd = retry_timeout(
                lambda: os.open(path, flags | lock | os.O_NONBLOCK),
                timeout=timeout
            )
            # we used non blocking mode (O_NONBLOCK) for open but non
            # blocking mode was not requested.
            if not block:
                try:
                    fcntl.fcntl(
                        fd, fcntl.F_SETFL,
                        fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK
                    )
                except BaseException:
                    os.close(fd)
                    raise
            return fd
        else:
            return os.open(path, flags | lock)

    return open(path, mode, opener=opener, **kwargs)


def open_locked_nt(path: AnyStr, mode="r", timeout=0., **kwargs) -> IO:
    """
    open_locked implementation using win32 CreateFileW, unlike posix/bsd
    implementations this is a mandatory lock.
    """
    if timeout < 0:
        timeout = 1e10

    def opener(path: AnyStr, flags: int) -> int:
        if flags & os.O_WRONLY:
            access = win32file.GENERIC_WRITE
            if flags & os.O_APPEND:
                # remove FILE_WRITE_DATA and leave FILE_APPEND_DATA
                access &= ~win32file.FILE_WRITE_DATA
            share = 0
        elif flags & os.O_RDWR:
            access = win32file.GENERIC_READ | win32file.GENERIC_WRITE
            share = 0
        else:
            access = win32file.GENERIC_READ
            share = win32file.FILE_SHARE_READ

        if flags & os.O_CREAT and flags & os.O_EXCL:
            cdisp = win32file.CREATE_NEW
        elif flags & os.O_CREAT:
            cdisp = win32file.OPEN_ALWAYS
        else:
            cdisp = win32file.OPEN_EXISTING

        secattr = pywintypes.SECURITY_ATTRIBUTES()
        secattr.SECURITY_DESCRIPTOR = None
        secattr.bInheritHandle = not flags & os.O_NOINHERIT

        def create_file():
            try:
                return win32file.CreateFileW(
                    path, access, share, secattr, cdisp, 0)
            except win32file.error as err:
                if err.winerror == winerror.ERROR_SHARING_VIOLATION:
                    raise BlockingIOError(
                        errno.EAGAIN, os.strerror(errno.EAGAIN))
                elif err.winerror in (winerror.ERROR_PATH_NOT_FOUND,
                                      winerror.ERROR_FILE_NOT_FOUND):
                    raise FileNotFoundError(
                        errno.ENOENT, os.strerror(errno.ENOENT))
                elif err.winerror == winerror.ERROR_FILE_EXISTS:
                    raise FileExistsError(
                        errno.EEXIST, os.strerror(errno.EEXIST))
                elif err.winerror == winerror.ERROR_ACCESS_DENIED:
                    raise PermissionError(
                        errno.EACCES, os.strerror(errno.EACCES))

        handle = retry_timeout(
            create_file,
            errors=(BlockingIOError,),
            timeout=timeout
        )
        fd = msvcrt.open_osfhandle(handle.handle, flags)
        handle.Detach()
        if flags & os.O_TRUNC:
            os.ftruncate(fd, 0)
        if flags & os.O_APPEND:
            os.lseek(fd, 0, os.SEEK_END)
        return fd

    return open(path, mode, opener=opener, **kwargs)


if os.name == "posix" and hasattr(os, "O_SHLOCK") and hasattr(os, "O_EXLOCK"):
    _open_locked = open_locked_bsd
elif os.name == "posix":
    _open_locked = open_locked_posix
elif os.name == "nt":
    _open_locked = open_locked_nt


def open_locked(path: AnyStr, mode="r", timeout=0, **kwargs) -> IO:
    """
    Open a file at path and acquire a read (shared) or write (exclusive) lock
    for the requested mode.

    On `posix` the lock is acquired using flock facility and is an advisory
    lock only. On Windows the file is open using CreateFileW and the lock
    is mandatory.

    Parameters
    ----------
    path: str
    mode: str
    timeout: float
        A timeout (in seconds) for lock acquire.
    kwargs:
        Other keywords passed to `open`

    Returns
    -------
    filelike: IO
        A filelike stream. The lock will be released once the file is closed.

    Raises
    ------
    BlockingIOError
        If `timeout=0` and the lock could not be acquired.
    TimeoutError
        If a lock could not be acquired in the specified timeout period
    """
    return _open_locked(path, mode, timeout=timeout, **kwargs)

open_locked.__module__ = "orangecanvas.shtools"
