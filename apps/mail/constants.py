"""Stable domain values for the mail UI."""

IMAP_INBOX = "INBOX"
FOLDER_FLAG_NOSELECT = "\\Noselect"
MESSAGE_FLAG_SEEN = "\\Seen"
MESSAGE_FLAG_FLAGGED = "\\Flagged"

# Search fields are intentionally bounded before they reach IMAP. They are domain
# validation limits, not deployment settings.
SEARCH_QUERY_MAX_LENGTH = 200
SEARCH_ADDRESS_MAX_LENGTH = 320
SEARCH_SUBJECT_MAX_LENGTH = 500

# Search scope values are part of the query-string contract.
SEARCH_SCOPE_FOLDER = "folder"
SEARCH_SCOPE_ALL = "all"

# A global search cannot scan an unbounded mailbox in one request. Keep at most
# this many newest matches per folder; the UI reports when a folder was capped.
GLOBAL_SEARCH_PER_FOLDER_LIMIT = 100

# The command palette is an incremental search affordance, not a full result
# page. Keep its response short enough to stay useful above the fold.
PALETTE_MESSAGE_LIMIT = 8
PALETTE_FOLDER_LIMIT = 6
MAX_BATCH_UIDS = 200
FOLDER_NAME_MAX_LENGTH = 64
DEFAULT_IMAP_DELIMITER = "/"


# The image proxy only forwards plain HTTP(S) and only raster formats. SVG is
# excluded because serving it same-origin could execute script if navigated.
IMAGE_PROXY_ALLOWED_SCHEMES = frozenset({"http", "https"})
IMAGE_PROXY_ALLOWED_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)

ATTACHMENT_PREVIEW_IMAGE_TYPES = IMAGE_PROXY_ALLOWED_CONTENT_TYPES
ATTACHMENT_PREVIEW_PDF_TYPES = frozenset({"application/pdf"})
ATTACHMENT_PREVIEW_TEXT_TYPES = frozenset(
    {"text/plain", "text/csv", "text/markdown", "application/json"}
)
ATTACHMENT_PREVIEW_AUDIO_TYPES = frozenset({"audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4"})
ATTACHMENT_PREVIEW_VIDEO_TYPES = frozenset({"video/mp4", "video/webm", "video/ogg"})
ATTACHMENT_INLINE_ALLOWED_CONTENT_TYPES = (
    ATTACHMENT_PREVIEW_IMAGE_TYPES
    | ATTACHMENT_PREVIEW_PDF_TYPES
    | ATTACHMENT_PREVIEW_AUDIO_TYPES
    | ATTACHMENT_PREVIEW_VIDEO_TYPES
)
ATTACHMENT_PREVIEW_MAX_TEXT_BYTES = 262_144
