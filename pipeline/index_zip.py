"""Read only the central directory of a remote TSE zip (via HTTP range requests) and save the member index.

usage: python index_zip.py <zip URL> <index.pkl>
"""
import pickle, sys, zipfile
from httpzip import HTTPFile

url, out = sys.argv[1:3]
f = HTTPFile(url)
z = zipfile.ZipFile(f)
idx = [(i.filename, i.header_offset, i.compress_size, i.file_size) for i in z.infolist()]
pickle.dump(idx, open(out, 'wb'))
print(f'{len(idx)} entries; {f.bytes_fetched / 1e6:.1f} MB read of {f.size / 1e9:.2f} GB')
