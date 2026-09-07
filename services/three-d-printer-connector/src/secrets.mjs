import fs from 'node:fs';
import path from 'node:path';

// Only selected references are read, on demand after certificate verification.
export class FileSecretStore {
  constructor(root) { this.root = fs.realpathSync(root); }
  get(reference) {
    let fd;
    try {
      if (!/^printer-\d{2}$/.test(reference)) throw new Error();
      const target = path.join(this.root, `${reference}.json`);
      if (fs.lstatSync(target).isSymbolicLink() || path.dirname(fs.realpathSync(target)) !== this.root) throw new Error();
      fd = fs.openSync(target, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.size > 16384 || (process.platform !== 'win32' && (stat.mode & 0o077))) throw new Error();
      const bytes = Buffer.alloc(16385);
      const size = fs.readSync(fd, bytes, 0, bytes.length, 0);
      if (size > 16384) throw new Error();
      const value = JSON.parse(bytes.subarray(0, size).toString('utf8'));
      if (Object.keys(value).sort().join(',') !== 'access_code,serial' ||
          !/^[a-zA-Z0-9_-]{1,64}$/.test(value.serial) || typeof value.access_code !== 'string' ||
          !value.access_code.length || value.access_code.length > 128) throw new Error();
      return Object.freeze(value);
    } catch { throw new Error('device_secret_unavailable'); }
    finally { if (fd !== undefined) fs.closeSync(fd); }
  }
}
