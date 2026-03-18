import sys
from pathlib import Path

def try_decompress(filepath):
    data = Path(filepath).read_bytes()
    print(f"Loaded {len(data)} bytes.")

    # 1. Zstandard
    try:
        import zstandard as zstd
        dctx = zstd.ZstdDecompressor()
        dec = dctx.decompress(data)
        print("Success: Zstandard decoded %d bytes" % len(dec))
        print("Preview:", dec[:200])
        return
    except Exception as e:
        print("Zstandard failed:", e)

    # 2. Brotli
    try:
        import brotli
        dec = brotli.decompress(data)
        print("Success: Brotli decoded %d bytes" % len(dec))
        print("Preview:", dec[:200])
        return
    except Exception as e:
        print("Brotli failed:", e)
        
    # 3. LZ4
    try:
        import lz4.frame
        dec = lz4.frame.decompress(data)
        print("Success: LZ4 decoded %d bytes" % len(dec))
        print("Preview:", dec[:200])
        return
    except Exception as e:
        print("LZ4 failed:", e)

    # 4. Try stripping framing headers (e.g. 4 bytes, 8 bytes)
    print("Trying offset decompression...")
    import brotli
    import zstandard as zstd
    
    for offset in range(1, 64):
        chunk = data[offset:]
        
        # zstd
        try:
            dctx = zstd.ZstdDecompressor()
            dec = dctx.decompress(chunk)
            print(f"Success: Zstd decoded at offset {offset}")
            Path(filepath + ".dec").write_bytes(dec)
            return
        except Exception: pass
        
        # brotli
        try:
            dec = brotli.decompress(chunk)
            print(f"Success: Brotli decoded at offset {offset}")
            Path(filepath + ".dec").write_bytes(dec)
            return
        except Exception: pass

    print("All decompression methods failed.")

if __name__ == '__main__':
    try_decompress(sys.argv[1])
