"""Mail read-model services."""

from apps.mail.services.mailbox import (
    FolderNode,
    MessagePage,
    MessageSummary,
    build_folder_tree,
    list_folders,
    list_messages,
)
from apps.mail.services.search import (
    SearchFilters,
    SearchResult,
    search_messages,
)

__all__ = [
    "FolderNode",
    "MessagePage",
    "MessageSummary",
    "SearchFilters",
    "SearchResult",
    "build_folder_tree",
    "list_folders",
    "list_messages",
    "search_messages",
]
