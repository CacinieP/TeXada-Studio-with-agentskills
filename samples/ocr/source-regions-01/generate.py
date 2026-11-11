"""Generate an original x+1 raster and synthetic region/review fixture.

This draws known glyphs, not OCR or human annotation. Use in a fresh directory;
no font, imaging library, compiler or model is required.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=False)
width, height = 40, 20
raster = [bytearray([255] * width) for _ in range(height)]
glyphs = ['10001 01010 00100 01010 10001 00000 00000',
          '00000 00100 00100 11111 00100 00100 00000',
          '00100 01100 00100 00100 00100 00100 01110']
for start, glyph in zip((4, 14, 24), glyphs):
    for y, row in enumerate(glyph.split(), 6):
        for x, bit in enumerate(row, start):
            if bit == '1':
                raster[y][x] = 0

def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))

header = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
image = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
         + chunk(b'IDAT', zlib.compress(b''.join(b'\0' + row for row in raster))) + chunk(b'IEND', b''))
(output / 'source.png').write_bytes(image)
record = {'status': 'OK', 'id': 'synthetic-known-glyphs', 'model': 'fixture-not-ocr', 'lines': ['$x+1$']}
digest = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':')).encode()).hexdigest()
review = {'record_sha256': digest, 'source_image_sha256': hashlib.sha256(image).hexdigest(),
          'reviewer': 'synthetic-rendering-fixture-not-human',
          'decisions': [{'start_line': 1, 'end_line': 1, 'action': 'accept', 'type': 'formula',
                         'bbox': [3, 5, 30, 14]}]}
for name, data in [('record.json', record), ('fixture-review.json', review)]:
    (output / name).write_text(json.dumps(data, indent=2) + '\n')
