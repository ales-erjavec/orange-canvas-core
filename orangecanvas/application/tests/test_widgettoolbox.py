"""
Tests for WidgetsToolBox.

"""
from AnyQt.QtWidgets import QWidget, QHBoxLayout
from AnyQt.QtCore import QSize, QStringListModel, QModelIndex

from ...registry import tests as registry_tests
from ...registry.qt import QtWidgetRegistry


from ..widgettoolbox import WidgetToolBox, WidgetToolGrid, ToolGrid

from ...gui import test


class TestWidgetToolBox(test.QAppTestCase):
    def test_widgettoolgrid(self):
        w = QWidget()
        layout = QHBoxLayout()
        reg = registry_tests.small_testing_registry()

        qt_reg = QtWidgetRegistry(reg)

        triggered_actions1 = []
        triggered_actions2 = []

        model = qt_reg.model()
        data_descriptions = qt_reg.widgets("Constants")

        one_action = qt_reg.action_for_widget("one")

        actions = list(map(qt_reg.action_for_widget, data_descriptions))

        grid = ToolGrid(w)
        grid.setActions(actions)
        grid.actionTriggered.connect(triggered_actions1.append)
        layout.addWidget(grid)

        grid = WidgetToolGrid(w)

        # First category ("Data")
        grid.setModel(model, rootIndex=model.index(0, 0))

        self.assertIs(model, grid.model())

        # Test order of buttons
        grid_layout = grid.layout()
        for i in range(len(actions)):
            button = grid_layout.itemAtPosition(i // 4, i % 4).widget()
            self.assertIs(button.defaultAction(), actions[i])

        grid.actionTriggered.connect(triggered_actions2.append)

        layout.addWidget(grid)

        w.setLayout(layout)
        w.show()
        one_action.trigger()
        self.qWait()

    def test_toolbox(self):
        reg = registry_tests.small_testing_registry()
        qt_reg = QtWidgetRegistry(reg)

        triggered_actions = []

        model = qt_reg.model()

        box = WidgetToolBox()
        box.setModel(model)
        model.setParent(box)
        box.triggered.connect(triggered_actions.append)

        box.setButtonSize(QSize(50, 80))
        box.show()

        box.setButtonSize(QSize(60, 80))
        box.setIconSize(QSize(35, 35))
        box.setTabButtonHeight(40)
        box.setTabIconSize(QSize(30, 30))

        a0, a1 = box.tabAction(0), box.tabAction(1)
        assert a0.isChecked()
        a1.trigger()
        del a1, a0
        state = box.saveState()
        # box.setModel(QStringListModel())
        # box.setModel(model)
        self.assertTrue(box.restoreState(state))
        a0, a1 = box.tabAction(0), box.tabAction(1)
        self.assertTrue(a0.isChecked())
        self.assertTrue(a1.isChecked())
        del a0, a1
        # model.clear()
        self.qWait()
        box.setModel(QStringListModel())

    def test_toolbox_model(self):
        box = WidgetToolBox()

        model = QStringListModel()
        box.setModel(model)
        self.assertEqual(box.count(), 0)
        model.insertRow(0, QModelIndex())
        self.assertEqual(box.count(), 1)
        box.setModel(QStringListModel())
        self.assertEqual(box.count(), 0)
        box.setModel(model)
        model.insertRow(0, QModelIndex())
        self.assertEqual(box.count(), 2)
