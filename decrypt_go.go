package main

import (
"bytes"
"crypto/aes"
"crypto/cipher"
"crypto/sha1"
"encoding/hex"
"fmt"
"io/ioutil"
"log"
"os"

"golang.org/x/crypto/pbkdf2"
)

func main() {
if len(os.Args) < 2 {
log.Fatal("Usage: ./decrypt_go <file.pb>")
}
data, err := ioutil.ReadFile(os.Args[1])
if err != nil {
log.Fatal(err)
}

// Try using the 64-byte key directly
rawKey, _ := hex.DecodeString("d85d5331e63d9c1995faacaebfcdd3b93f117f882cde27c93602a2fd5cac26aecab99d42a4a54d9558781afc33641b1eff877a31c532d43c8be4d71fa8dcf66f")

// Create Chromium's Linux key
chromiumKey := pbkdf2.Key([]byte("xodSODizgPb1mw8n8H6hMQ=="), []byte("saltysalt"), 1, 16, sha1.New)

keys := [][]byte{
rawKey[:16], rawKey[:32], rawKey, chromiumKey,
}

fmt.Printf("File size: %d, first 16 bytes: %x\n", len(data), data[:16])

// The file starts with protobuf: tag 509 (size), tag 3 (bytes 75), tag 12 (bytes 41301).
// Let's grab the 41301 bytes as it's the largest chunk

// Fast-forward to the large chunk (around offset 81)
idx := bytes.Index(data, []byte{0x1a, 0x62, 0x42, 0xd1}) // offset 7 found earlier
if idx != -1 {
    fmt.Printf("Found first chunk at %d\n", idx)
}

// Let's just try AES-GCM on the whole file, skipping some offsets
for _, key := range keys {
block, err := aes.NewCipher(key)
if err != nil {
continue
}
for _, nonceSize := range []int{12, 16} {
gcm, err := cipher.NewGCMWithNonceSize(block, nonceSize)
if err != nil {
continue
}
for offset := 0; offset < 200; offset++ {
if len(data) < offset+nonceSize+16 {
continue
}
nonce := data[offset : offset+nonceSize]
ciphertext := data[offset+nonceSize:]

_, err := gcm.Open(nil, nonce, ciphertext, nil)
if err == nil {
fmt.Printf("DECRYPTED! KeyLen=%d, NonceSize=%d, Offset=%d\n", len(key), nonceSize, offset)
os.Exit(0)
}
}
}
}

// Try a simpler approach: does the first 12 bytes match a nonce, then rest is ciphertext?
    // Go's GCM.Seal appends the 16-byte tag to the ciphertext.

fmt.Println("No standard AES-GCM decryption succeeded.")
}
