import io, subprocess, time

class HTTPFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, fetched with curl (block-cached)."""
    def __init__(self, url, block=1 << 20):
        self.url = url; self.pos = 0; self.block = block; self.cache = {}; self.bytes_fetched = 0
        h = self._curl(['-sSI', url]).decode('latin1')
        self.size = int([l.split(':', 1)[1] for l in h.lower().splitlines() if l.startswith('content-length')][-1])

    def _curl(self, args):
        for attempt in range(6):
            r = subprocess.run(['curl', '-sSf', '-m', '300'] + args, capture_output=True)
            if r.returncode == 0:
                return r.stdout
            if attempt == 5:
                raise IOError(r.stderr.decode())
            time.sleep(2 ** attempt)

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]; return self.pos

    def _get(self, start, end):
        d = self._curl(['-r', f'{start}-{end-1}', self.url])
        if len(d) != end - start:
            raise IOError(f'short read {len(d)} != {end-start}')
        self.bytes_fetched += len(d); return d

    def read(self, n=-1):
        if n < 0: n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0: return b''
        if n > 4 * self.block:
            d = self._get(self.pos, self.pos + n); self.pos += n; return d
        out = bytearray(); p = self.pos; end = p + n
        while p < end:
            b = p // self.block
            if b not in self.cache:
                if len(self.cache) > 64: self.cache.clear()
                self.cache[b] = self._get(b * self.block, min(self.size, (b + 1) * self.block))
            blk = self.cache[b]; o = p - b * self.block; take = min(end - p, len(blk) - o)
            out += blk[o:o + take]; p += take
        self.pos = end; return bytes(out)

    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)

    def get_member(self, header_offset, compress_size):
        """Fetch one zip member's raw bytes in a single request: local header + data."""
        import struct, zlib
        hdr = self._get(header_offset, header_offset + 30)
        sig, ver, flag, meth, _, _, crc, csz, usz, nlen, xlen = struct.unpack('<IHHHHHIIIHH', hdr)
        assert sig == 0x04034b50
        start = header_offset + 30 + nlen + xlen
        raw = self._get(start, start + compress_size)
        if meth == 0: return raw
        if meth == 8: return zlib.decompress(raw, -15)
        raise ValueError(f'compression method {meth}')
