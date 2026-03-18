/**
 * decrypt_pb.mjs - Uses Electron Node.js (safeStorage equivalent) to decrypt
 * Antigravity .pb conversation files.
 *
 * Strategy: The .pb files use crypto.subtle AES-GCM-256.
 * The JWK encryption key is stored encrypted (via Electron's encryptionService)
 * in some persistent storage. We use the Chromium OS Crypt key (from the
 * GNOME keyring "Chromium Safe Storage" for Antigravity) to derive the AES key
 * and try to decrypt directly.
 *
 * Run with: node --experimental-vm-modules decrypt_pb.mjs <pb_file>
 */

import { createDecipheriv, pbkdf2Sync } from 'crypto';
import { readFileSync, readdirSync } from 'fs';
import { resolve, join } from 'path';
import { homedir } from 'os';

// Chromium Safe Storage secret for Antigravity (from GNOME keyring)
const CHROMIUM_SAFE_STORAGE = Buffer.from('xodSODizgPb1mw8n8H6hMQ==');
const SALT = Buffer.from('saltysalt');

// Derive AES keys using PBKDF2-SHA1 (Chromium Linux method)
const key16_1 = pbkdf2Sync(CHROMIUM_SAFE_STORAGE, SALT, 1, 16, 'sha1');
const key16_1003 = pbkdf2Sync(CHROMIUM_SAFE_STORAGE, SALT, 1003, 16, 'sha1');
const key32_1 = pbkdf2Sync(CHROMIUM_SAFE_STORAGE, SALT, 1, 32, 'sha1');

// The 64-byte Electron EncryptionService key from keyring (app_id='')
const ELECTRON_KEY_HEX = 'd85d5331e63d9c1995faacaebfcdd3b93f117f882cde27c93602a2fd5cac26aecab99d42a4a54d9558781afc33641b1eff877a31c532d43c8be4d71fa8dcf66f';
const ELECTRON_KEY = Buffer.from(ELECTRON_KEY_HEX, 'hex');

const IV_SPACES = Buffer.alloc(16, ' ');

function tryDecryptCBC(data, key, offset = 0) {
    const chunk = data.slice(offset);
    const alignedLen = Math.floor(chunk.length / 16) * 16;
    try {
        const decipher = createDecipheriv('aes-128-cbc', key, IV_SPACES);
        decipher.setAutoPadding(false);
        const dec = Buffer.concat([decipher.update(chunk.slice(0, alignedLen)), decipher.final()]);
        const printable = [...dec.slice(0, 200)].filter(b => b >= 32 && b < 127 || b === 10 || b === 13).length;
        if (printable / 200 > 0.5) {
            return dec;
        }
    } catch (e) { }
    return null;
}

function tryDecryptGCM(data, key, nonceLen = 12) {
    try {
        const nonce = data.slice(0, nonceLen);
        const tag = data.slice(-16);
        const ciphertext = data.slice(nonceLen, -16);
        const decipher = createDecipheriv(`aes-${key.length * 8}-gcm`, key, nonce);
        decipher.setAuthTag(tag);
        const dec = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
        return dec;
    } catch (e) {
        return null;
    }
}

function analyzeFile(filePath) {
    const data = readFileSync(filePath);
    console.log(`\n=== ${filePath} (${data.length} bytes) ===`);
    console.log(`First 32 bytes: ${data.slice(0, 32).toString('hex')}`);

    const tests = [
        { name: 'AES-128-CBC(key16_1, iv=spaces, off=0)', fn: () => tryDecryptCBC(data, key16_1, 0) },
        { name: 'AES-128-CBC(key16_1, iv=spaces, off=3)', fn: () => tryDecryptCBC(data, key16_1, 3) },
        { name: 'AES-128-CBC(key16_1003, iv=spaces, off=0)', fn: () => tryDecryptCBC(data, key16_1003, 0) },
    ];

    const gcmTests = [
        { key: key16_1, name: 'AES-128-GCM(key16_1)' },
        { key: key16_1003, name: 'AES-128-GCM(key16_1003)' },
        { key: key32_1, name: 'AES-256-GCM(key32_1)' },
        { key: ELECTRON_KEY.slice(0, 16), name: 'AES-128-GCM(ELECTRON_16)' },
        { key: ELECTRON_KEY.slice(0, 32), name: 'AES-256-GCM(ELECTRON_32)' },
        { key: ELECTRON_KEY.slice(32), name: 'AES-256-GCM(ELECTRON_32+)' },
    ];

    for (const { name, fn } of tests) {
        const result = fn();
        if (result) {
            console.log(`✅ SUCCESS: ${name}`);
            console.log(`Preview: ${result.slice(0, 200).toString('utf8').replace(/\n/g, '\\n')}`);
            return;
        }
    }

    for (const { key, name } of gcmTests) {
        for (const nonceLen of [12, 16]) {
            const result = tryDecryptGCM(data, key, nonceLen);
            if (result) {
                console.log(`✅ SUCCESS: ${name} (nonce=${nonceLen})`);
                console.log(`Preview: ${result.slice(0, 200).toString('utf8').replace(/\n/g, '\\n')}`);
                return;
            }
        }
    }

    console.log('❌ All decryption attempts failed');
}

// Analyze files
const convDir = join(homedir(), '.gemini', 'antigravity', 'conversations');
try {
    const files = readdirSync(convDir).filter(f => f.endsWith('.pb'));
    console.log(`Found ${files.length} .pb files`);
    for (const f of files.slice(0, 3)) {
        analyzeFile(join(convDir, f));
    }
} catch (e) {
    const target = process.argv[2];
    if (target) analyzeFile(target);
    else console.error('No conversation directory found and no file specified');
}
