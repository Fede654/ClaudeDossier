import sys
from google.protobuf.internal.decoder import _DecodeVarint32

def extract_pb_texts(data):
    texts = []
    
    def parse_message(buffer):
        pos = 0
        while pos < len(buffer):
            try:
                tag, new_pos = _DecodeVarint32(buffer, pos)
                pos = new_pos
                wire_type = tag & 0b111
                if wire_type == 0:  # Varint
                    _, pos = _DecodeVarint32(buffer, pos)
                elif wire_type == 1:  # 64-bit
                    pos += 8
                elif wire_type == 5:  # 32-bit
                    pos += 4
                elif wire_type == 2:  # Length-delimited
                    length, new_pos = _DecodeVarint32(buffer, pos)
                    pos = new_pos
                    field_data = buffer[pos:pos+length]
                    pos += length
                    
                    # Try to decode as a nested message first
                    # But if it fails or has very few fields, we also try UTF-8 string
                    
                    # Is it a string?
                    try:
                        text = field_data.decode('utf-8')
                        if len(text) > 10 and any(c.isalpha() for c in text):
                            texts.append(text)
                    except UnicodeDecodeError:
                        pass
                    
                    # Also try to recurse in case it is a nested message
                    parse_message(field_data)
                    
                else:
                    break # Invalid wire type, stop parsing this message
            except:
                break

    parse_message(data)
    
    # Filter and deduplicate
    final_texts = []
    seen = set()
    for t in texts:
        if t not in seen:
            seen.add(t)
            final_texts.append(t)
            
    return final_texts

if __name__ == '__main__':
    with open('/home/fede/.gemini/antigravity/conversations/4dd503fa-2f73-4cd6-957d-06d165b63f72.pb', 'rb') as f:
        data = f.read()
    
    # The file could be framed (multiple length-delimited messages) 
    # Try parsing the whole file as a single message first, 
    # but since it might have varint length headers, we can try both.
    
    print("Method 1: Direct Parse")
    t1 = extract_pb_texts(data)
    print(f"Found {len(t1)} texts.")
    if t1:
        print("First text:", t1[0][:100])
        
    print("\nMethod 2: Framed Parse")
    t2 = []
    pos = 0
    while pos < len(data):
        try:
            msg_len, pos = _DecodeVarint32(data, pos)
            msg_data = data[pos:pos+msg_len]
            pos += msg_len
            t2.extend(extract_pb_texts(msg_data))
        except:
            break
    print(f"Found {len(t2)} texts.")
    if t2:
        print("First text:", t2[0][:100])
