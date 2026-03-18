import os
import sys
import plyvel
import glob

def scan_leveldb():
    ldb_paths = glob.glob(os.path.expanduser('~/.config/Antigravity/Local Storage/leveldb'))
    for ldb_path in ldb_paths:
        print(f"Scanning leveldb: {ldb_path}")
        try:
            db = plyvel.DB(ldb_path)
            for key, value in db:
                k_lower = key.lower()
                if b'conversation' in k_lower or b'history' in k_lower or b'chat' in k_lower:
                    print(f"KEY: {key}")
                    if len(value) > 100:
                        print(f"VALUE: {value[:200]}")
            db.close()
        except Exception as e:
            print(f"LevelDB Error: {e}")

if __name__ == '__main__':
    scan_leveldb()

