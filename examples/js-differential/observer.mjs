import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

try {
  if (process.argv[2] === '--identity') {
    console.log(JSON.stringify({ node: process.version, v8: process.versions.v8,
      unicode: process.versions.unicode, os: process.platform, arch: process.arch }));
  } else {
    const timeout = Number(process.argv[3]);
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 60000) throw Error('invalid timeout');
    const result = runInNewContext(readFileSync(process.argv[2], 'utf8'), Object.create(null), { timeout });
    if (typeof result !== 'string') throw Error('script must return a JSON string');
    for (let i = 0; i < result.length; i++) {
      const c = result.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff) {
        const next = result.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff)) throw Error('unpaired surrogate in JSON transport');
      } else if (c >= 0xdc00 && c <= 0xdfff) throw Error('unpaired surrogate in JSON transport');
    }
    JSON.parse(result);
    process.stdout.write(result + '\n');
  }
} catch (error) {
  process.stderr.write(String(error) + '\n');
  process.exitCode = 2;
}
