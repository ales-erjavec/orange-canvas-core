"""
Undo/Redo Commands

"""
import typing
from abc import abstractmethod
from typing import Callable, Optional, Tuple, List, Any

from AnyQt.QtWidgets import QUndoCommand

if typing.TYPE_CHECKING:
    from ..scheme import (
        Scheme, SchemeNode, SchemeLink, BaseSchemeAnnotation,
        SchemeTextAnnotation, SchemeArrowAnnotation
    )
    Pos = Tuple[float, float]
    Rect = Tuple[float, float, float, float]
    Line = Tuple[Pos, Pos]


class UndoCommand(QUndoCommand):
    """
    For serialization
    """
    def __init__(self, text, parent=None):
        super().__init__(text, parent)

    @abstractmethod
    def deconstruct(self) -> '_Command':
        return UndoCommand, (self.text(), ), dict(self.__dict__), UndoCommand._deconstruct_children(self)

    def _deconstruct_children(self) -> List["_Command"]:
        return [undocommand_deconstruct(
            self.child(i)) for i in range(self.childCount())]


_Command = Tuple[type, tuple, dict, List['_Command']]


def undocommand_deconstruct(command: QUndoCommand) -> _Command:
    if type(command) == QUndoCommand:
        return UndoCommand.deconstruct(command)
    elif isinstance(command, UndoCommand):
        return command.deconstruct()
    else:
        raise TypeError


def undocommand_reconstruct(command: _Command, parent=None):
    class_, args, state, children = command
    command = class_(*args, parent=parent)
    command.__dict__.update(state)
    for c in children:
        _ = undocommand_reconstruct(c, parent=command)
    return command


class AddNodeCommand(UndoCommand):
    def __init__(self, scheme, node, parent=None):
        # type: (Scheme, SchemeNode, Optional[UndoCommand]) -> None
        super().__init__("Add %s" % node.title, parent)
        self.scheme = scheme
        self.node = node

    def redo(self):
        self.scheme.add_node(self.node)

    def undo(self):
        self.scheme.remove_node(self.node)

    def deconstruct(self):
        return AddNodeCommand, (self.scheme, self.node), {}, []


class RemoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, parent=None):
        # type: (Scheme, SchemeNode, Optional[UndoCommand]) -> None
        super().__init__("Remove %s" % node.title, parent)
        self.scheme = scheme
        self.node = node
        self._index = -1
        links = scheme.input_links(self.node) + \
                scheme.output_links(self.node)

        for link in links:
            RemoveLinkCommand(scheme, link, parent=self)

    def redo(self):
        # redo child commands
        super().redo()
        self._index = self.scheme.nodes.index(self.node)
        self.scheme.remove_node(self.node)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_node(self._index, self.node)
        # Undo child commands
        super().undo()

    def deconstruct(self) -> '_Command':
        return (RemoveNodeCommand, (self.scheme, self.node,),
                dict(self.__dict__), [])


class AddLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent=None):
        # type: (Scheme, SchemeLink, Optional[UndoCommand]) -> None
        super().__init__("Add link", parent)
        self.scheme = scheme
        self.link = link

    def redo(self):
        self.scheme.add_link(self.link)

    def undo(self):
        self.scheme.remove_link(self.link)

    def deconstruct(self) -> '_Command':
        return (AddLinkCommand, (self.scheme, self.link,),
                dict(self.__dict__), [])


class RemoveLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent=None):
        # type: (Scheme, SchemeLink, Optional[UndoCommand]) -> None
        super().__init__("Remove link", parent)
        self.scheme = scheme
        self.link = link
        self._index = -1

    def redo(self):
        self._index = self.scheme.links.index(self.link)
        self.scheme.remove_link(self.link)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_link(self._index, self.link)
        self._index = -1

    def deconstruct(self) -> '_Command':
        return (RemoveLinkCommand, (self.scheme, self.link,),
                dict(self.__dict__), [])


class InsertNodeCommand(UndoCommand):
    def __init__(
            self,
            scheme,     # type: Scheme
            new_node,   # type: SchemeNode
            old_link,   # type: SchemeLink
            new_links,  # type: Tuple[SchemeLink, SchemeLink]
            parent=None # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Insert widget into link", parent)
        self.scheme = scheme
        self.new_node = new_node
        self.old_link = old_link
        self.new_links = new_links
        AddNodeCommand(scheme, new_node, parent=self)
        RemoveLinkCommand(scheme, old_link, parent=self)
        for link in new_links:
            AddLinkCommand(scheme, link, parent=self)

    def deconstruct(self) -> '_Command':
        return (InsertNodeCommand,
                (self.scheme, self.new_node, self.old_link, self.new_links),
                dict(self.__dict__), [])


class AddAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent=None):
        # type: (Scheme, BaseSchemeAnnotation, Optional[UndoCommand]) -> None
        super().__init__("Add annotation", parent)
        self.scheme = scheme
        self.annotation = annotation

    def redo(self):
        self.scheme.add_annotation(self.annotation)

    def undo(self):
        self.scheme.remove_annotation(self.annotation)

    def deconstruct(self) -> '_Command':
        return (AddAnnotationCommand, (self.scheme, self.annotation,),
                dict(self.__dict__), [])


class RemoveAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent=None):
        # type: (Scheme, BaseSchemeAnnotation, Optional[UndoCommand]) -> None
        super().__init__("Remove annotation", parent)
        self.scheme = scheme
        self.annotation = annotation
        self._index = -1

    def redo(self):
        self._index = self.scheme.annotations.index(self.annotation)
        self.scheme.remove_annotation(self.annotation)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_annotation(self._index, self.annotation)
        self._index = -1

    def deconstruct(self) -> '_Command':
        return (RemoveAnnotationCommand, (self.scheme, self.annotation,),
                dict(self.__dict__), [])


class MoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, old, new, parent=None):
        # type: (Scheme, SchemeNode, Pos, Pos, Optional[UndoCommand]) -> None
        super().__init__("Move", parent)
        self.scheme = scheme
        self.node = node
        self.old = old
        self.new = new

    def redo(self):
        self.node.position = self.new

    def undo(self):
        self.node.position = self.old

    def deconstruct(self) -> '_Command':
        return (MoveNodeCommand, (self.scheme, self.node, self.old, self.new),
                dict(self.__dict__), [])


class ResizeCommand(UndoCommand):
    def __init__(self, scheme, item, new_geom, parent=None):
        # type: (Scheme, SchemeTextAnnotation, Rect, Optional[UndoCommand]) -> None
        super().__init__("Resize", parent)
        self.scheme = scheme
        self.item = item
        self.new_geom = new_geom
        self.old_geom = item.rect

    def redo(self):
        self.item.rect = self.new_geom

    def undo(self):
        self.item.rect = self.old_geom


class ArrowChangeCommand(UndoCommand):
    def __init__(self, scheme, item, new_line, parent=None):
        # type: (Scheme, SchemeArrowAnnotation, Line, Optional[UndoCommand]) -> None
        super().__init__("Move arrow", parent)
        self.scheme = scheme
        self.item = item
        self.new_line = new_line
        self.old_line = (item.start_pos, item.end_pos)

    def redo(self):
        self.item.set_line(*self.new_line)

    def undo(self):
        self.item.set_line(*self.old_line)

    def deconstruct(self) -> '_Command':
        return (ArrowChangeCommand, (self.scheme, self.item, self.new_line,),
                dict(self.__dict__), [])


class AnnotationGeometryChange(UndoCommand):
    def __init__(
            self,
            scheme,  # type: Scheme
            annotation,  # type: BaseSchemeAnnotation
            old,  # type: Any
            new,  # type: Any
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Change Annotation Geometry", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.old = old
        self.new = new

    def redo(self):
        self.annotation.geometry = self.new  # type: ignore

    def undo(self):
        self.annotation.geometry = self.old  # type: ignore

    def deconstruct(self) -> '_Command':
        return (AnnotationGeometryChange,
                (self.scheme, self.annotation, self.old, self.new),
                dict(self.__dict__), [])


class RenameNodeCommand(UndoCommand):
    def __init__(self, scheme, node, old_name, new_name, parent=None):
        # type: (Scheme, SchemeNode, str, str, Optional[UndoCommand]) -> None
        super().__init__("Rename", parent)
        self.scheme = scheme
        self.node = node
        self.old_name = old_name
        self.new_name = new_name

    def redo(self):
        self.node.set_title(self.new_name)

    def undo(self):
        self.node.set_title(self.old_name)

    def deconstruct(self) -> '_Command':
        return (RemoveNodeCommand, (self.scheme, self.node, self.old_name, self.new_name),
                dict(self.__dict__), [])


class TextChangeCommand(UndoCommand):
    def __init__(
            self,
            scheme,       # type: Scheme
            annotation,   # type: SchemeTextAnnotation
            old_content,  # type: str
            old_content_type,  # type: str
            new_content,  # type: str
            new_content_type,  # type: str
            parent=None   # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Change text", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.old_content = old_content
        self.old_content_type = old_content_type
        self.new_content = new_content
        self.new_content_type = new_content_type

    def redo(self):
        self.annotation.set_content(self.new_content, self.new_content_type)

    def undo(self):
        self.annotation.set_content(self.old_content, self.old_content_type)

    def deconstruct(self) -> '_Command':
        return (TextChangeCommand,
                (self.scheme, self.annotation,
                 self.old_content, self.old_content_type,
                 self.new_content, self.new_content_type),
                dict(self.__dict__), [])


class SetAttrCommand(UndoCommand):
    def __init__(
            self,
            obj,         # type: Any
            attrname,    # type: str
            newvalue,    # type: Any
            name=None,   # type: Optional[str]
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        if name is None:
            name = "Set %r" % attrname
        super().__init__(name, parent)
        self.obj = obj
        self.attrname = attrname
        self.newvalue = newvalue
        self.oldvalue = getattr(obj, attrname)

    def redo(self):
        setattr(self.obj, self.attrname, self.newvalue)

    def undo(self):
        setattr(self.obj, self.attrname, self.oldvalue)


class SetWindowGroupPresets(UndoCommand):
    def __init__(
            self,
            scheme: 'Scheme',
            presets: List['Scheme.WindowGroup'],
            parent: Optional[UndoCommand] = None,
            **kwargs
    ) -> None:
        text = kwargs.pop("text", "Set Window Presets")
        super().__init__(text, parent, **kwargs)
        self.scheme = scheme
        self.presets = presets
        self.__undo_presets = None

    def redo(self):
        presets = self.scheme.window_group_presets()
        self.scheme.set_window_group_presets(self.presets)
        self.__undo_presets = presets

    def undo(self):
        self.scheme.set_window_group_presets(self.__undo_presets)
        self.__undo_presets = None


class SimpleUndoCommand(UndoCommand):
    """
    Simple undo/redo command specified by callable function pair.
    Parameters
    ----------
    redo: Callable[[], None]
        A function expressing a redo action.
    undo : Callable[[], None]
        A function expressing a undo action.
    text : str
        The command's text (see `UndoCommand.setText`)
    parent : Optional[UndoCommand]
    """

    def __init__(
            self,
            redo,  # type: Callable[[], None]
            undo,  # type: Callable[[], None]
            text,  # type: str
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__(text, parent)
        self._redo = redo
        self._undo = undo

    def undo(self):
        # type: () -> None
        """Reimplemented."""
        self._undo()

    def redo(self):
        # type: () -> None
        """Reimplemented."""
        self._redo()
