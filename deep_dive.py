import sys
import zlib
import gzip
from pathlib import Path

def analyze_file(filepath):
    data = Path(filepath).read_bytes()
    print(f"File size: {len(data)} bytes")
    
    # Signatures
    gzip_sig = b'\x1f\x8b'
    zlib_sigs = [b'\x78\x01', b'\x78\x9c', b'\x78\xda']
    zstd_sig = b'\x28\xb5\x2f\xfd'
    
    for sig in [gzip_sig] + zlib_sigs + [zstd_sig]:
        idx = 0
        while True:
            idx = data.find(sig, idx)
            if idx == -1:
                break
            print(f"Found signature {sig.hex()} at offset {idx}")
            
            # Try to decompress
            try:
                if sig == gzip_sig:
                    dec = gzip.decompress(data[idx:])
                    print("  SUCCESS: GZIP decoded %d bytes" % len(dec))
                    print(dec[:200])
                elif sig in zlib_sigs:
                    dec = zlib.decompress(data[idx:])
                    print("  SUCCESS: ZLIB decoded %d bytes" % len(dec))
                    print(dec[:200])
                elif sig == zstd_sig:
                    print("  FOUND ZSTD, need library to decode")
            except Exception as e:
                 print(f"  Failed: {e}")
            
            idx += 1
            
    # Try finding plaintext strings (length > 15)
    import re
    strings = re.findall(b'[ -~]{20,}', data)
    print(f"\nFound {len(strings)} printable string segments.")
    for s in strings[:10]:
        print(f"  String: {s[:100].decode(errors='replace')}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_file(sys.argv[1])
