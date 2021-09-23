"""
Qt Model classes for widget registry.

"""
import bisect
import warnings

from typing import Union

from xml.sax.saxutils import escape
from urllib.parse import urlencode

from AnyQt.QtWidgets import QAction
from AnyQt.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush
from AnyQt.QtCore import QObject, Qt
from AnyQt.QtCore import pyqtSignal as Signal
from orangecanvas.registry.description import NodeDescription

from ..utils import type_str
from .discovery import WidgetDiscovery
from .description import WidgetDescription, CategoryDescription
from .base import WidgetRegistry, NodeRegistry
from ..resources import icon_loader

from . import cache, NAMED_COLORS, DEFAULT_COLOR


class QtWidgetDiscovery(QObject, WidgetDiscovery):
    """
    Qt interface class for widget discovery.
    """
    # Discovery has started
    discovery_start = Signal()
    # Discovery has finished
    discovery_finished = Signal()
    # Processing widget with name
    discovery_process = Signal(str)
    # Found a widget with description
    found_widget = Signal(WidgetDescription)
    # Found a category with description
    found_category = Signal(CategoryDescription)

    def __init__(self, parent=None, registry=None, cached_descriptions=None):
        QObject.__init__(self, parent)
        WidgetDiscovery.__init__(self, registry, cached_descriptions)

    def run(self, entry_points_iter):
        self.discovery_start.emit()
        WidgetDiscovery.run(self, entry_points_iter)
        self.discovery_finished.emit()

    def handle_widget(self, description):
        self.discovery_process.emit(description.name)
        self.found_widget.emit(description)

    def handle_category(self, description):
        self.found_category.emit(description)


class QtRegistryHandler(QObject, WidgetDiscovery.RegistryHandler):
    # Found a widget with description
    found_widget = Signal(WidgetDescription)
    # Found a category with description
    found_category = Signal(CategoryDescription)

    def handle_category(self, category):
        super().handle_category(category)
        self.found_category.emit(category)

    def handle_widget(self, desc):
        super().handle_widget(desc)
        self.found_widget.emit(desc)


class QtNodeRegistry(NodeRegistry, QObject):
    """
    A QObject wrapper for `NodeRegistry`

    A QStandardItemModel instance containing the widgets in
    a tree (of depth 2). The items in a model can be queried using standard
    roles (DisplayRole, BackgroundRole, DecorationRole ToolTipRole).
    They also have QtNodeRegistry.CATEGORY_DESC_ROLE,
    QtNodeRegistry.NODE_DESC_ROLE, which store Category/NodeDescription
    respectfully. Furthermore QtNodeRegistry.NODE_ACTION_ROLE stores an
    default QAction which can be used for node creation action.
    """

    #: Category Description Role
    CATEGORY_DESC_ROLE = Qt.ItemDataRole(Qt.UserRole + 1)

    #: Node Description Role
    NODE_DESC_ROLE = Qt.ItemDataRole(Qt.UserRole + 2)
    WIDGET_DESC_ROLE = NODE_DESC_ROLE

    #: Widget Action Role
    NODE_ACTION_ROLE = Qt.ItemDataRole(Qt.UserRole + 3)
    WIDGET_ACTION_ROLE = NODE_ACTION_ROLE

    #: Background color for widget/category in the canvas (different
    #: from Qt.BackgroundRole)
    BACKGROUND_ROLE = Qt.ItemDataRole(Qt.UserRole + 4)

    category_added = Signal(str, CategoryDescription)
    node_added = Signal(str, str, NodeDescription)

    def __init__(self, other=None, *, parent=None, **kwargs):
        super().__init__(other, **kwargs)
        self.setParent(parent)

        # Should  the QStandardItemModel be subclassed?
        self.__item_model = QStandardItemModel(self)

        for i, desc in enumerate(self.categories()):
            cat_item = self._cat_desc_to_std_item(desc)
            self.__item_model.insertRow(i, cat_item)

            for j, wdesc in enumerate(self.nodes(desc.name)):
                node_item = self._node_desc_to_std_item(wdesc, desc)
                cat_item.insertRow(j, node_item)

    def model(self):
        # type: () -> QStandardItemModel
        """
        Return the widget descriptions in a Qt Item Model instance
        (QStandardItemModel).

        .. note:: The model should not be modified outside of the registry.
        """
        return self.__item_model

    def item_for_widget(self, widget):
        # type: (Union[str, WidgetDescription]) -> QStandardItem
        return self.item_for_node(widget)

    def item_for_node(self, node: NodeDescription) -> QStandardItem:
        """Return the QStandardItem for the node."""
        if isinstance(node, str):
            node = self.node(node)
        cat = self.category(node.category or "Unspecified")
        cat_ind = self.categories().index(cat)
        cat_item = self.model().item(cat_ind)
        widget_ind = self.nodes(cat).index(node)
        return cat_item.child(widget_ind)

    def action_for_widget(self, widget):
        return self.action_for_node(widget)

    def action_for_node(self, node: NodeDescription) -> QAction:
        """
        Return the QAction instance for the widget (can be a string or
        a `NodeDescription` instance).
        """
        item = self.item_for_node(node)
        return item.data(self.NODE_ACTION_ROLE)

    def create_action_for_item(self, item):
        # type: (QStandardItem) -> QAction
        """
        Create a QAction instance for the widget description item.
        """
        name = item.text()
        tooltip = item.toolTip()
        whatsThis = item.whatsThis()
        icon = item.icon()
        action = QAction(
            icon, name, self, toolTip=tooltip, whatsThis=whatsThis,
            statusTip=name
        )
        widget_desc = item.data(self.NODE_DESC_ROLE)
        action.setData(widget_desc)
        action.setProperty("item", item)
        return action

    def _insert_category(self, desc):
        # type: (CategoryDescription) -> None
        """
        Override to update the item model and emit the signals.
        """
        priority = desc.priority
        priorities = [c.priority for c, _ in self.registry]
        insertion_i = bisect.bisect_right(priorities, priority)

        WidgetRegistry._insert_category(self, desc)

        cat_item = self._cat_desc_to_std_item(desc)
        self.__item_model.insertRow(insertion_i, cat_item)

        self.category_added.emit(desc.name, desc)

    def _insert_node(self, category, desc):
        # type: (CategoryDescription, NodeDescription) -> None
        """
        Override to update the item model and emit the signals.
        """
        categories = self.categories()
        cat_i = categories.index(category)
        _, widgets = self._categories_dict[category.name]
        priorities = [w.priority for w in widgets]
        insertion_i = bisect.bisect_right(priorities, desc.priority)

        super()._insert_node(category, desc)
        desc = self.widget(desc.qualified_name)
        cat_item = self.__item_model.item(cat_i)
        widget_item = self._node_desc_to_std_item(desc, category)

        cat_item.insertRow(insertion_i, widget_item)

        self.node_added.emit(category.name, desc.name, desc)

    def _cat_desc_to_std_item(self, desc):
        # type: (CategoryDescription) -> QStandardItem
        """
        Create a QStandardItem for the category description.
        """
        item = QStandardItem()
        item.setText(desc.name)

        if desc.icon:
            icon = desc.icon
        else:
            icon = "icons/default-category.svg"

        icon = icon_loader.from_description(desc).get(icon)
        item.setIcon(icon)

        if desc.background:
            background = desc.background
        else:
            background = DEFAULT_COLOR

        background = NAMED_COLORS.get(background, background)

        brush = QBrush(QColor(background))
        item.setData(brush, self.BACKGROUND_ROLE)

        tooltip = desc.description if desc.description else desc.name

        item.setToolTip(tooltip)
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(desc, self.CATEGORY_DESC_ROLE)
        return item

    def _node_desc_to_std_item(self, desc, category):
        # type: (NodeDescription, CategoryDescription) -> QStandardItem
        """
        Create a QStandardItem for the node description.
        """
        item = QStandardItem(desc.name)
        item.setText(desc.name)

        if desc.icon:
            icon = desc.icon
        else:
            icon = "icons/default-widget.svg"

        icon = icon_loader.from_description(desc).get(icon)
        item.setIcon(icon)

        # This should be inherited from the category.
        background = None
        if desc.background:
            background = desc.background
        elif category.background:
            background = category.background
        else:
            background = DEFAULT_COLOR

        if background is not None:
            background = NAMED_COLORS.get(background, background)
            brush = QBrush(QColor(background))
            item.setData(brush, self.BACKGROUND_ROLE)

        tooltip = tooltip_helper(desc)
        style = "ul { margin-top: 1px; margin-bottom: 1px; }"
        tooltip = TOOLTIP_TEMPLATE.format(style=style, tooltip=tooltip)
        item.setToolTip(tooltip)
        item.setWhatsThis(whats_this_helper(desc))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item.setData(desc, self.WIDGET_DESC_ROLE)

        # Create the action for the widget_item
        action = self.create_action_for_item(item)
        item.setData(action, self.WIDGET_ACTION_ROLE)
        return item


QtWidgetRegistry = QtNodeRegistry


TOOLTIP_TEMPLATE = """\
<html>
<head>
<style type="text/css">
{style}
</style>
</head>
<body>
{tooltip}
</body>
</html>
"""


def tooltip_helper(desc: NodeDescription) -> str:
    """Node tooltip construction helper."""
    tooltip = []
    tooltip.append("<b>{name}</b>".format(name=escape(desc.name)))

    if desc.project_name and desc.project_name != "Orange":
        tooltip[0] += " (from {0})".format(desc.project_name)

    if desc.description:
        tooltip.append("{0}".format(
                            escape(desc.description)))

    inputs_fmt = "<li>{name} ({class_name})</li>"

    if desc.inputs:
        inputs = "".join(inputs_fmt.format(name=inp.name,
                                           class_name=type_str(inp.types))
                         for inp in desc.inputs)
        tooltip.append("Inputs:<ul>{0}</ul>".format(inputs))
    else:
        tooltip.append("No inputs")

    if desc.outputs:
        outputs = "".join(inputs_fmt.format(name=out.name,
                                            class_name=type_str(out.types))
                          for out in desc.outputs)
        tooltip.append("Outputs:<ul>{0}</ul>".format(outputs))
    else:
        tooltip.append("No outputs")

    return "<hr/>".join(tooltip)


def whats_this_helper(desc, include_more_link=False):
    # type: (NodeDescription, bool) -> str
    """
    A `What's this` text construction helper. If `include_more_link` is
    True then the text will include a `more...` link.

    """
    title = desc.name
    help_url = desc.extra.get("help_url", "")

    if not help_url:
        help_url = "help://search?" + urlencode({"id": desc.id})

    description = desc.description
    long_description = desc.long_description

    template = ["<h3>{0}</h3>".format(escape(title))]

    if description:
        template.append("<p>{0}</p>".format(escape(description)))

    if long_description:
        template.append("<p>{0}</p>".format(escape(long_description[:100])))

    if help_url and include_more_link:
        template.append("<a href='{0}'>more...</a>".format(escape(help_url)))

    return "\n".join(template)
