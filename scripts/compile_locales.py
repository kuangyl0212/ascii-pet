"""Compile .po files to .mo files for gettext.

Implements a minimal .mo file writer following the GNU gettext MO format.
No external dependencies required — uses only Python stdlib.

Usage:
    python compile_locales.py
"""
import array
import re
import struct
from pathlib import Path


def parse_po(po_path):
    """Parse a .po file and return a list of (msgid, msgstr) tuples."""
    with open(po_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    # Match msgid "..." followed by msgstr "..."
    # Handle multi-line strings (concatenated quoted strings)
    pattern = re.compile(
        r'msgid\s+((?:"(?:[^"\\]|\\.)*"\s*)+)\s+'
        r'msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*)+)',
        re.DOTALL
    )

    for match in pattern.finditer(content):
        msgid_raw = _concat_strings(match.group(1))
        msgstr_raw = _concat_strings(match.group(2))
        entries.append((msgid_raw, msgstr_raw))

    return entries


def _concat_strings(raw):
    """Concatenate multiple quoted strings into one, handling escape sequences."""
    # Extract individual quoted strings
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    combined = ''.join(strings)
    # Process escape sequences
    combined = combined.replace('\\n', '\n')
    combined = combined.replace('\\t', '\t')
    combined = combined.replace('\\"', '"')
    combined = combined.replace('\\\\', '\\')
    return combined


def write_mo(mo_path, entries):
    """Write entries as a .mo file in GNU gettext MO format.

    Format reference: https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
    """
    # Filter out empty msgid (header entry goes first with empty msgid)
    # Sort: empty msgid first, then alphabetical by msgid
    header_entry = None
    regular_entries = []
    for msgid, msgstr in entries:
        if msgid == '':
            header_entry = (msgid, msgstr)
        else:
            regular_entries.append((msgid, msgstr))

    regular_entries.sort(key=lambda x: x[0])

    if header_entry:
        all_entries = [header_entry] + regular_entries
    else:
        all_entries = regular_entries

    # Build the MO file
    # Magic number for little-endian: 0x950412de
    # Magic number for big-endian: 0xde120495
    magic = 0x950412de

    N = len(all_entries)

    # Encode all strings to bytes
    encoded = []
    for msgid, msgstr in all_entries:
        encoded.append((msgid.encode('utf-8'), msgstr.encode('utf-8')))

    # Calculate offsets
    # Header: 7 * 4 = 28 bytes
    header_size = 28
    # Original strings table: N * 8 bytes (length + offset pairs)
    orig_table_offset = header_size
    # Translation strings table: N * 8 bytes
    trans_table_offset = orig_table_offset + N * 8
    # String data starts after both tables
    string_data_offset = trans_table_offset + N * 8

    # Calculate string offsets
    orig_entries = []
    trans_entries = []
    current_offset = 0

    # First pass: calculate offsets for original strings
    orig_data = b''
    for msgid_bytes, msgstr_bytes in encoded:
        orig_entries.append((len(msgid_bytes), current_offset))
        orig_data += msgid_bytes + b'\x00'
        current_offset += len(msgid_bytes) + 1

    # Second pass: calculate offsets for translation strings
    trans_data = b''
    current_offset = 0
    for msgid_bytes, msgstr_bytes in encoded:
        trans_entries.append((len(msgstr_bytes), current_offset))
        trans_data += msgstr_bytes + b'\x00'
        current_offset += len(msgstr_bytes) + 1

    # Build the file
    mo_file = bytearray()

    # Header
    mo_file += struct.pack('<I', magic)           # magic
    mo_file += struct.pack('<I', 0)               # revision
    mo_file += struct.pack('<I', N)               # number of strings
    mo_file += struct.pack('<I', orig_table_offset)   # offset of orig table
    mo_file += struct.pack('<I', trans_table_offset)  # offset of trans table
    mo_file += struct.pack('<I', 0)               # size of hash table (0 = no hash)
    mo_file += struct.pack('<I', 0)               # offset of hash table

    # Original strings table
    for length, offset in orig_entries:
        mo_file += struct.pack('<I', length)
        mo_file += struct.pack('<I', string_data_offset + offset)

    # Translation strings table
    for length, offset in trans_entries:
        mo_file += struct.pack('<I', length)
        mo_file += struct.pack('<I', string_data_offset + len(orig_data) + offset)

    # String data
    mo_file += orig_data
    mo_file += trans_data

    # Write to file
    mo_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mo_path, 'wb') as f:
        f.write(bytes(mo_file))


def compile_all():
    """Compile all .po files in the locales directory to .mo files."""
    locales_dir = Path(__file__).parent.parent / 'locales'

    for po_path in locales_dir.glob('*/LC_MESSAGES/*.po'):
        mo_path = po_path.with_suffix('.mo')
        print(f'Compiling {po_path} -> {mo_path}')
        entries = parse_po(po_path)
        write_mo(mo_path, entries)
        print(f'  {len(entries)} entries compiled')


if __name__ == '__main__':
    compile_all()
