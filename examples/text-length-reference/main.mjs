// Independently observe Node.js string operations; no Go/Gooo implementation.
import { readFileSync } from 'node:fs';

try {
  const inputs = JSON.parse(readFileSync(0, 'utf8'));
  if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > 128) {
    throw new Error('INVALID_CORPUS');
  }
  const seen = new Set();
  const encoder = new TextEncoder();
  const rows = inputs.map(({ id, text }) => {
    if (typeof id !== 'string' || !id || typeof text !== 'string') {
      throw new Error('INVALID_INPUT');
    }
    if (seen.has(id)) throw new Error('DUPLICATE_ID');
    seen.add(id);
    // TextEncoder replaces unpaired surrogates; reject them before encoding.
    for (const scalar of text) {
      const value = scalar.codePointAt(0);
      if (value >= 0xd800 && value <= 0xdfff) throw new Error('INVALID_UNICODE_SCALAR');
    }
    const bytes = encoder.encode(text).length;
    if (bytes > 1024) throw new Error('BYTE_LIMIT');
    return { id, text, lengths: {
      utf8_bytes: bytes,
      code_points: Array.from(text).length,
      utf16_units: text.length,
    } };
  });
  process.stdout.write(JSON.stringify({
    runtime: { node: process.version, v8: process.versions.v8, unicode: process.versions.unicode },
    rows,
  }) + '\n');
} catch (error) {
  process.stderr.write(JSON.stringify({ decision: 'FAIL_CLOSED', code: error.message }) + '\n');
  process.exitCode = 1;
}
