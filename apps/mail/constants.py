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

# The image proxy only forwards plain HTTP(S) and only raster formats. SVG is
# excluded because serving it same-origin could execute script if navigated.
IMAGE_PROXY_ALLOWED_SCHEMES = frozenset({"http", "https"})
IMAGE_PROXY_ALLOWED_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
