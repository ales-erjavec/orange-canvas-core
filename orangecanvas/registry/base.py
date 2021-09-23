"""
===============
Widget Registry
===============

"""
import logging
import bisect

from operator import attrgetter

import typing
from typing import Optional, List, Tuple, Dict, Union

from . description import (
    CategoryDescription, NodeDescription, WidgetDescription
)
from . import description

if typing.TYPE_CHECKING:
    CategoryNodesPair = Tuple[CategoryDescription, List[NodeDescription]]

log = logging.getLogger(__name__)

# Registry hex version
VERSION_HEX = 0x000108


class NodeRegistry(object):
    """
    A container for node and category descriptions.

    Parameters
    ----------
    other : Optional[pNodeRegistry]
        If supplied the registry is initialized with the contents of `other`.

    See also
    --------
    WidgetDiscovery
    """
    def __init__(self, other: Optional['NodeRegistry'] = None, **kwargs):
        super().__init__(**kwargs)
        # A list of (category, node_list) tuples ordered by priority.
        self.registry = []  # type: List[CategoryNodesPair]

        # tuples from 'registry' indexed by name
        self._categories_dict = {}  # type: Dict[str, CategoryNodesPair]

        # WidgetDescriptions by qualified name
        self._nodes_dict = {}  # type: Dict[str, NodeDescription]

        if other is not None:
            if not isinstance(other, NodeRegistry):
                raise TypeError("Expected a 'NodeRegistry' got %r." \
                                % type(other).__name__)

            self.registry = list(other.registry)
            self._categories_dict = dict(other._categories_dict)
            self._nodes_dict = dict(other._nodes_dict)

    def categories(self):
        # type: () -> List[CategoryDescription]
        """
        Return a list all top level :class:`CategoryDescription` instances
        ordered by `priority`.

        """
        return [c for c, _ in self.registry]

    def category(self, name):
        # type: (str) -> CategoryDescription
        """
        Find and return a :class:`CategoryDescription` by its `name`.

        .. note:: Categories are identified by `name` attribute in contrast
                  with widgets which are identified by `qualified_name`.

        Parameters
        ----------
        name : str
            Category name

        """
        return self._categories_dict[name][0]

    def has_category(self, name):
        # type: (str) -> bool
        """
        Return ``True`` if a category with `name` exist in this registry.

        Parameters
        ----------
        name : str
            Category name

        """
        return name in self._categories_dict

    def widgets(self, category=None):
        """
        Return a list of all widgets in the registry. If `category` is
        specified return only widgets which belong to the category.

        Parameters
        ----------
        category : :class:`CategoryDescription` or str, optional
            Return only descriptions of widgets belonging to the category.
        """
        items = self.nodes(category)
        return [item for item in items if isinstance(item, WidgetDescription)]

    def nodes(self, category=None):
        # type: (Union[CategoryDescription, str, None]) -> List[NodeDescription]
        if category is None:
            categories = self.categories()
        elif isinstance(category, str):
            categories = [self.category(category)]
        else:
            categories = [category]

        items = []
        for cat in categories:
            if isinstance(cat, str):
                cat = self.category(cat)
            cat_widgets = self._categories_dict[cat.name][1]
            items.extend(sorted(cat_widgets,
                                  key=attrgetter("priority")))
        return items

    def widget(self, qualified_name):
        return self.node(qualified_name)

    def node(self, qualified_name: str) -> NodeDescription:
        """
        Return a :class:`NodeDescription` identified by `qualified_name`.

        Raise :class:`KeyError` if the description does not exist.

        Parameters
        ----------
        qualified_name : str
            Node description qualified name
        """
        return self._nodes_dict[qualified_name]

    def has_widget(self, qualified_name):
        # type: (str) -> bool
        """
        Return ``True`` if the widget with `qualified_name` exists in
        this registry.
        """
        return qualified_name in self._nodes_dict

    def has_node(self, qualified_name):
        return qualified_name in self._nodes_dict

    def register_widget(self, desc):
        # type: (WidgetDescription) -> None
        """
        Register a :class:`WidgetDescription` instance.

        .. deprecated:: 0.2
           Use `register_node`
        """
        if not isinstance(desc, description.WidgetDescription):
            raise TypeError("Expected a 'WidgetDescription' got %r." \
                            % type(desc).__name__)
        if self.has_widget(desc.qualified_name):
            raise ValueError("%r already exists in the registry." \
                             % desc.qualified_name)
        self.register_node(desc)

    def register_node(self, desc: NodeDescription) -> None:
        """Register a :class:`NodeDescription` instance."""
        category = desc.category
        if category is None:
            category = "Unspecified"

        if self.has_category(category):
            cat_desc = self.category(category)
        else:
            log.warning("Creating a default category %r.", category)
            cat_desc = description.CategoryDescription(name=category)
            self.register_category(cat_desc)

        self._insert_node(cat_desc, desc)

    def register_category(self, desc: CategoryDescription):
        """
        Register a :class:`CategoryDescription` instance.

        .. note:: It is always best to register the category
                  before the widgets belonging to it.

        """
        if not isinstance(desc, description.CategoryDescription):
            raise TypeError("Expected a 'CategoryDescription' got %r." \
                            % type(desc).__name__)

        name = desc.name
        if not name:
            log.info("Creating a default category name.")
            name = "default"

        if any(name == c.name for c in self.categories()):
            log.info("A category with %r name already exists" % name)
            return

        self._insert_category(desc)

    def _insert_category(self, desc):
        # type: (CategoryDescription) -> None
        """
        Insert category description into 'registry' list
        """
        priority = desc.priority
        priorities = [c.priority for c, _ in self.registry]
        insertion_i = bisect.bisect_right(priorities, priority)

        item = (desc, [])  # type: CategoryNodesPair
        self.registry.insert(insertion_i, item)
        self._categories_dict[desc.name] = item

    def _insert_node(self, category, desc):
        # type: (CategoryDescription, NodeDescription) -> None
        """
        Insert widget description `desc` into `category`.
        """
        _, items = self._categories_dict[category.name]

        if desc.background is None:
            desc.background = category.background
        if desc.category is None:
            desc.category = category.name

        priority = desc.priority
        priorities = [d.priority for d in items]
        insertion_i = bisect.bisect_right(priorities, priority)
        items.insert(insertion_i, desc)
        self._nodes_dict[desc.qualified_name] = desc

    def _insert_widget(self, category, desc):
        self._insert_node(category, desc)


# Back-compat alias
WidgetRegistry = NodeRegistry
