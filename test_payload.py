import sys
import zlib
from google.protobuf.internal.decoder import _DecodeVarint32

with open('/home/fede/.gemini/antigravity/conversations/4dd503fa-2f73-4cd6-957d-06d165b63f72.pb', 'rb') as f:
    data = f.read()

pos = 0
chunks = []
while pos < len(data):
    try:
        tag, new_pos = _DecodeVarint32(data, pos)
        wire_type = tag & 0b111
        if wire_type == 2:
            length, data_pos = _DecodeVarint32(data, new_pos)
            pos = data_pos + length
            if length > 1000:
                chunks.append(data[data_pos:pos])
        elif wire_type == 0:
            _, pos = _DecodeVarint32(data, new_pos)
        elif wire_type == 1:
            pos = new_pos + 8
        elif wire_type == 5:
            pos = new_pos + 4
        elif wire_type == 3 or wire_type == 4:
            pos = new_pos
        else:
            pos += 1
    except:
        pos += 1

print(f"Found {len(chunks)} large chunks.")
for i, chunk in enumerate(chunks[:5]):
    print(f"Chunk {i} length: {len(chunk)}, starts with: {chunk[:10].hex()}")
    
    # Try GZIP
    import gzip
    try:
        res = gzip.decompress(chunk)
        print(f"  -> GZIP! {len(res)} bytes")
    except: pass

    # Try ZLIB
    try:
        res = zlib.decompress(chunk)
        print(f"  -> ZLIB! {len(res)} bytes")
    except: pass
