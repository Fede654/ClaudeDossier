#!/usr/bin/env python3
"""
Schema-less protobuf wire walker.
Walks the raw wire format, extracting all LEN-delimited fields.
For each field, attempts to:
  1. Decode as UTF-8 string (display if printable)
  2. Parse as a nested protobuf message
  3. Display as hex bytes otherwise
"""
import sys
import struct
from pathlib import Path


def decode_varint(data, pos):
    """Decode a varint from data at pos, returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError(f"Premature EOF reading varint at pos {pos}")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        if shift >= 64:
            raise ValueError("Varint too long")
    return result, pos


def is_printable(b):
    """Check if bytes look like printable ASCII/UTF-8 text."""
    if len(b) == 0:
        return False
    try:
        text = b.decode('utf-8')
        # Require at least 4 chars and mostly printable
        printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
        return len(text) >= 4 and printable / len(text) > 0.8
    except Exception:
        return False


def walk_proto(data, depth=0, max_depth=12, field_path=""):
    """Walk protobuf wire format, yielding (path, wire_type, value) tuples."""
    results = []
    pos = 0
    field_count = 0
    INDENT = "  " * depth

    while pos < len(data):
        try:
            tag_val, pos = decode_varint(data, pos)
        except Exception:
            break

        field_no = tag_val >> 3
        wire_type = tag_val & 0x7

        path = f"{field_path}.{field_no}" if field_path else str(field_no)

        try:
            if wire_type == 0:  # Varint
                val, pos = decode_varint(data, pos)
                results.append((path, "varint", val))

            elif wire_type == 1:  # 64-bit
                if pos + 8 > len(data):
                    break
                val = struct.unpack_from('<Q', data, pos)[0]
                pos += 8
                results.append((path, "fixed64", val))

            elif wire_type == 2:  # Length-delimited (string, bytes, embedded message)
                length, pos = decode_varint(data, pos)
                if pos + length > len(data):
                    break
                payload = data[pos:pos + length]
                pos += length

                # Try to decode as UTF-8 string
                if is_printable(payload):
                    text = payload.decode('utf-8', errors='replace')
                    results.append((path, "string", text))
                    # Also try to recurse if it could be a nested message
                    if depth < max_depth and length > 2:
                        try:
                            sub = walk_proto(payload, depth + 1, max_depth, path)
                            if sub:
                                results.extend(sub)
                        except Exception:
                            pass
                else:
                    # Try to recurse as nested message
                    if depth < max_depth and length > 2:
                        try:
                            sub = walk_proto(payload, depth + 1, max_depth, path)
                            if sub:
                                results.extend(sub)
                            else:
                                results.append((path, "bytes", payload[:64].hex()))
                        except Exception:
                            results.append((path, "bytes", payload[:64].hex()))
                    else:
                        results.append((path, "bytes", payload[:64].hex()))

            elif wire_type == 5:  # 32-bit
                if pos + 4 > len(data):
                    break
                val = struct.unpack_from('<I', data, pos)[0]
                pos += 4
                results.append((path, "fixed32", val))

            else:
                # Unknown wire type, skip
                break

        except Exception as e:
            break

        field_count += 1
        if field_count > 100000:  # Safety cap
            break

    return results


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        # Find first .pb file
        base = Path.home() / ".gemini" / "antigravity" / "conversations"
        files = sorted(base.glob("*.pb"))
        if not files:
            print("No .pb files found")
            return
        target = str(files[0])

    print(f"Analyzing: {target}")
    data = Path(target).read_bytes()
    print(f"Size: {len(data)} bytes\n")

    results = walk_proto(data)

    print(f"=== All extracted strings (field path -> value) ===\n")
    string_count = 0
    for path, kind, val in results:
        if kind == "string":
            text = str(val)
            # Filter: only show non-trivial strings
            if len(text) > 3:
                print(f"[{path}] {repr(text[:300])}")
                string_count += 1

    print(f"\n=== Summary ===")
    print(f"Total fields found: {len(results)}")
    print(f"String fields: {string_count}")

    # Print all field paths to understand structure
    print(f"\n=== Field structure (type counts) ===")
    from collections import Counter
    type_counts = Counter(kind for _, kind, _ in results)
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    # Show top-level field numbers
    print(f"\n=== Top-level field numbers ===")
    top_level = [f for f, _, _ in results if '.' not in f]
    top_counts = Counter(top_level)
    for f, c in top_counts.most_common(20):
        print(f"  field {f}: {c} occurrences")


if __name__ == "__main__":
    main()
