import sys
from google.protobuf.internal.decoder import _DecodeVarint32

def parse_all_strings(data):
    texts = []
    pos = 0
    end = len(data)
    
    while pos < end:
        try:
            # We try to find anything that looks like a length-delimited string
            tag, new_pos = _DecodeVarint32(data, pos)
            wire_type = tag & 0b111
            
            if wire_type == 0:
                _, new_pos = _DecodeVarint32(data, new_pos)
                pos = new_pos
            elif wire_type == 1:
                pos = new_pos + 8
            elif wire_type == 5:
                pos = new_pos + 4
            elif wire_type == 3 or wire_type == 4:
                # Group start/end - just ignore the boundary and keep reading inner tags
                pos = new_pos
            elif wire_type == 2:
                length, data_pos = _DecodeVarint32(data, new_pos)
                pos = data_pos + length
                if length > 10 and length < 1000000:
                    field_data = data[data_pos:pos]
                    try:
                        text = field_data.decode('utf-8')
                        # Heuristic to check if it's conversational text
                        if any(c.isspace() for c in text) and any(c.isalpha() for c in text):
                            texts.append(text)
                    except UnicodeDecodeError:
                        # Might be a nested message, let's also try to parse it from data_pos!
                        # But wait, if we just advance `pos = data_pos + length`, we skip it.
                        # If we want to NOT skip it, we can just let the main loop parse it?
                        # No, if it's a nested message, it is a valid byte stream.
                        pass
            else:
                # Invalid wire type. We got desynchronized.
                # Just skip 1 byte and try again to resync!
                pos += 1
        except Exception as e:
            # End of buffer or invalid varint
            pos += 1

    return texts

if __name__ == '__main__':
    with open('/home/fede/.gemini/antigravity/conversations/4dd503fa-2f73-4cd6-957d-06d165b63f72.pb', 'rb') as f:
        data = f.read()
    
    found_texts = parse_all_strings(data)
    print(f"Found {len(found_texts)} texts.")
    if found_texts:
        print("First 3:")
        for t in found_texts[:3]:
            print("  --- ", t[:100].replace('\n', ' '))
