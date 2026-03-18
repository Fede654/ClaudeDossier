package main

import (
    "crypto/aes"
    "crypto/cipher"
    "crypto/sha1"
    "encoding/hex"
    "fmt"
    "io/ioutil"
    "os"
    "golang.org/x/crypto/pbkdf2"
)

func main() {
    if len(os.Args) < 2 {
        os.Exit(1)
    }
    data, err := ioutil.ReadFile(os.Args[1])
    if err != nil {
        os.Exit(1)
    }

    rawKey, _ := hex.DecodeString("d85d5331e63d9c1995faacaebfcdd3b93f117f882cde27c93602a2fd5cac26aecab99d42a4a54d9558781afc33641b1eff877a31c532d43c8be4d71fa8dcf66f")
    chromiumKey := pbkdf2.Key([]byte("xodSODizgPb1mw8n8H6hMQ=="), []byte("saltysalt"), 1, 16, sha1.New)
    chromiumKey1003 := pbkdf2.Key([]byte("xodSODizgPb1mw8n8H6hMQ=="), []byte("saltysalt"), 1003, 16, sha1.New)
    chromiumKey32 := pbkdf2.Key([]byte("xodSODizgPb1mw8n8H6hMQ=="), []byte("saltysalt"), 1, 32, sha1.New)
    
    keys := [][]byte{
        rawKey[:16], rawKey[:32], rawKey, chromiumKey, chromiumKey1003, chromiumKey32,
    }

    fmt.Printf("File size: %d\n", len(data))

    // Aggressive search for AES-GCM decryption
    for i, key := range keys {
        block, err := aes.NewCipher(key)
        if err != nil { continue }
        
        for _, nonceSize := range []int{12, 16} {
            gcm, err := cipher.NewGCMWithNonceSize(block, nonceSize)
            if err != nil { continue }
            
            for offset := 0; offset < len(data) - nonceSize - 16; offset++ {
                if offset > 5000 { break }
                
                nonce := data[offset : offset+nonceSize]
                ciphertextAndTag := data[offset+nonceSize:]
                
                for chunkLen := 16; chunkLen <= len(ciphertextAndTag); chunkLen += 16 {
                    if chunkLen > len(ciphertextAndTag) { chunkLen = len(ciphertextAndTag) }
                    
                    dec, err := gcm.Open(nil, nonce, ciphertextAndTag[:chunkLen], nil)
                    if err == nil {
                        // verify it's printable or valid to avoid false positives on small chunks
                        printable := 0
                        for _, b := range dec {
                            if (b >= 32 && b < 127) || b == 10 || b == 13 || b == 9 {
                                printable++
                            }
                        }
                        if len(dec) > 10 && float64(printable)/float64(len(dec)) > 0.5 {
                            fmt.Printf("\n>>> DECRYPTED! KeyIdx=%d, NonceSize=%d, Offset=%d, ChunkLen=%d\n", i, nonceSize, offset, chunkLen)
                            fmt.Printf("Preview: %q\n", dec[:100])
                            os.Exit(0)
                        }
                    }
                }
            }
        }
    }
    fmt.Println("No decryption succeeded.")
}
