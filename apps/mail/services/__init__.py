"""Mail read-model services."""

from apps.mail.services.mailbox import (
    FolderNode,
    MessagePage,
    MessageSummary,
    build_folder_tree,
    list_folders,
    list_messages,
)

__all__ = [
    "FolderNode",
    "MessagePage",
    "MessageSummary",
    "build_folder_tree",
    "list_folders",
    "list_messages",
]
