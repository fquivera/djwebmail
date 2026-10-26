#!/usr/bin/env python3
"""Compile .po catalogs to binary .mo catalogs without GNU gettext."""

from __future__ import annotations

import struct
from pathlib import Path


def unescape_po_string(text: str) -> str:
    """Unescape standard C/PO escape sequences without corrupting UTF-8 characters."""
    result = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "\\" and i + 1 < length:
            nxt = text[i + 1]
            if nxt == "n":
                result.append("\n")
            elif nxt == "t":
                result.append("\t")
            elif nxt == "r":
                result.append("\r")
            elif nxt == '"':
                result.append('"')
            elif nxt == "\\":
                result.append("\\")
            else:
                result.append("\\" + nxt)
            i += 2
        else:
            result.append(char)
            i += 1
    return "".join(result)


def compile_po_to_mo(po_path: Path, mo_path: Path) -> int:
    """Compile a .po file into GNU gettext binary .mo format."""
    content = po_path.read_text(encoding="utf-8")
    messages: dict[str, str] = {}
    current_id: str | None = None
    current_str: str | None = None
    state: str | None = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("msgid "):
            if current_id is not None and current_str is not None:
                messages[unescape_po_string(current_id)] = unescape_po_string(current_str)
            raw = line[6:].strip()
            if raw.startswith('"') and raw.endswith('"'):
                current_id = raw[1:-1]
            else:
                current_id = raw
            current_str = ""
            state = "id"
        elif line.startswith("msgstr "):
            raw = line[7:].strip()
            if raw.startswith('"') and raw.endswith('"'):
                current_str = raw[1:-1]
            else:
                current_str = raw
            state = "str"
        elif line.startswith('"') and line.endswith('"'):
            raw = line[1:-1]
            if state == "id" and current_id is not None:
                current_id += raw
            elif state == "str" and current_str is not None:
                current_str += raw

    if current_id is not None and current_str is not None:
        messages[unescape_po_string(current_id)] = unescape_po_string(current_str)

    # Sort keys for binary search required by GNU gettext
    keys = sorted(messages.keys())
    num_strings = len(keys)

    orig_bytes: list[bytes] = []
    trans_bytes: list[bytes] = []
    for k in keys:
        orig_bytes.append(k.encode("utf-8") + b"\x00")
        trans_bytes.append(messages[k].encode("utf-8") + b"\x00")

    # Header size: 7 integers of 4 bytes = 28 bytes
    header_size = 7 * 4
    orig_table_offset = header_size
    trans_table_offset = orig_table_offset + num_strings * 8

    current_data_offset = trans_table_offset + num_strings * 8

    orig_table: list[bytes] = []
    for b in orig_bytes:
        orig_table.append(struct.pack("<II", len(b) - 1, current_data_offset))
        current_data_offset += len(b)

    trans_table: list[bytes] = []
    for b in trans_bytes:
        trans_table.append(struct.pack("<II", len(b) - 1, current_data_offset))
        current_data_offset += len(b)

    header = struct.pack(
        "<IIIIIII",
        0x950412DE,  # magic
        0,  # revision
        num_strings,  # number of strings
        orig_table_offset,
        trans_table_offset,
        0,  # hashing table size
        0,  # hashing table offset
    )

    payload = (
        header
        + b"".join(orig_table)
        + b"".join(trans_table)
        + b"".join(orig_bytes)
        + b"".join(trans_bytes)
    )
    mo_path.write_bytes(payload)
    return num_strings


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    locale_dir = base_dir / "locale"
    for po_file in locale_dir.rglob("*.po"):
        mo_file = po_file.with_suffix(".mo")
        count = compile_po_to_mo(po_file, mo_file)
        po_rel = po_file.relative_to(base_dir)
        mo_rel = mo_file.relative_to(base_dir)
        print(f"Compiled {count} messages from {po_rel} to {mo_rel}")
