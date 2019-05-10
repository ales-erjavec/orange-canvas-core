"""
Orange Canvas Application

"""
from orangecanvas.gui.utils import macos_set_nswindow_tabbing

from AnyQt.QtWidgets import QApplication
from AnyQt.QtCore import Qt, QUrl, QEvent, pyqtSignal as Signal


class CanvasApplication(QApplication):
    fileOpenRequest = Signal(QUrl)

    def __init__(self, argv, **kwargs):
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            # Turn on HighDPI support when available
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        super().__init__(argv, **kwargs)
        self.setAttribute(Qt.AA_DontShowIconsInMenus, True)
        macos_set_nswindow_tabbing(False)

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            self.fileOpenRequest.emit(event.url())
        return super().event(event)
