"""Independent literal preview pixels, exported formats and unsafe input checks."""
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sw.preview import render, png, svg, preview
from sw.assets import load_shades
from sw.expressions import AssemblyError
ROOT=Path(__file__).resolve().parents[3]


class PreviewTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'workdir/builds/preview-unit'
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='space ',dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'source with spaces.json'
        self.data={'schema_version':1,'width':16,'height':16,'pixels':[[0]*16 for _ in range(16)]}
        self.data['pixels'][0][:4]=[0,1,2,3]
        self.data['pixels'][8][0]=3
        self.source.write_text(json.dumps(self.data))

    def test_literal_positions_frame_boundaries_and_mirror(self):
        c=render(self.data,width=8,height=8,scale=2,mirror=True)
        self.assertEqual((len(c[0]),len(c)),(42,22))
        self.assertEqual(c[2][2:6],[(228,228,240),(208,208,208),(104,104,104),(24,24,24)])
        self.assertEqual(c[2][22],(24,24,24))  # Bottom-left atlas frame becomes third.
        self.assertEqual(c[12][6:10],[(24,24,24),(104,104,104),(208,208,208),(188,188,208)])
        self.assertEqual(c[12][29],(24,24,24))

    def test_png_svg_literal_pixels_dimensions_and_determinism(self):
        c=render(self.data,scale=2,labels=['A'])
        encoded=png(c,2)
        self.assertEqual(encoded,png(c,2))
        self.assertEqual(encoded[:8],b'\x89PNG\r\n\x1a\n')
        offset=8; compressed=b''
        while offset<len(encoded):
            size=struct.unpack('>I',encoded[offset:offset+4])[0]
            name=encoded[offset+4:offset+8]; payload=encoded[offset+8:offset+8+size]
            crc=struct.unpack('>I',encoded[offset+8+size:offset+12+size])[0]
            self.assertEqual(crc,zlib.crc32(name+payload))
            if name==b'IHDR': self.assertEqual(struct.unpack('>IIBBBBB',payload),(40,54,8,2,0,0,0))
            if name==b'IDAT': compressed+=payload
            offset+=size+12
        raw=zlib.decompress(compressed)
        self.assertEqual(len(raw),54*121)
        self.assertEqual(raw[4*121+1+6*3:4*121+1+8*3],bytes([208,208,208])*2)
        self.assertEqual(raw[40*121+1+6*3:40*121+1+8*3],bytes([24,24,24])*2) # A top middle.
        document=ET.fromstring(svg(c,2))
        self.assertEqual(document.attrib['width'],'40')
        self.assertEqual(document.attrib['height'],'54')
        rendered={}
        for rect in document:
            a=rect.attrib
            for x in range(int(a['x']),int(a['x'])+int(a['width'])):
                rendered[x,int(a['y'])]=a['fill']
        self.assertEqual(rendered[3,2],'#d0d0d0')
        self.assertEqual(rendered[3,20],'#181818')
        self.assertEqual(svg(c,2),svg(c,2))

    def test_bad_geometry_labels_and_size(self):
        for options in [{'width':24},{'width':0},{'height':9},{'scale':0},
                        {'scale':True},{'scale':33},{'labels':[]},{'labels':['<x>']}]:
            with self.subTest(options=options),self.assertRaises(ValueError):render(self.data,**options)
        huge={'width':1024,'height':16,'pixels':[[0]*1024 for _ in range(16)]}
        with self.assertRaises(ValueError):render(huge,scale=32)

    def test_malformed_shades_and_duplicate_keys(self):
        for spelling in ['{',self.source.read_text().replace('"schema_version": 1','"schema_version": 1, "schema_version": 1'),
                         self.source.read_text().replace('[0, 1, 2, 3','[0, 1, 2, 4'),
                         self.source.read_text().replace('[0, 1, 2, 3','[0, true, 2, 3')]:
            self.source.write_text(spelling)
            with self.assertRaises(AssemblyError):load_shades(self.source,'fixture.json')

    def test_output_identity_spaces_repeat_and_unsafe_tags(self):
        with patch('sw.preview.subprocess.run',return_value=subprocess.CompletedProcess([],0,'abc123\n')):
            stage=preview(self.root,self.source,'first',scale=2)
            record=json.loads((stage/'result.json').read_text())
            self.assertEqual(record['status'],'PASS')
            self.assertEqual(record['source_sha256'],sha256(self.source.read_bytes()).hexdigest())
            for name,digest in record['outputs'].items():self.assertEqual(digest,sha256((stage/name).read_bytes()).hexdigest())
            self.assertEqual(len((stage/'tiles.2bpp').read_bytes()),64)
            for tag in ['first','../escape','a/b','C:/escape','']:
                with self.subTest(tag=tag),self.assertRaises((ValueError,FileExistsError)):
                    preview(self.root,self.source,tag)
            self.assertEqual(json.loads(self.source.read_text()),self.data)
            other=preview(self.root,self.source,'second',scale=2)
            for name in record['outputs']:self.assertEqual((stage/name).read_bytes(),(other/name).read_bytes())

    def test_missing_git_does_not_publish_pass(self):
        with patch('sw.preview.subprocess.run',side_effect=FileNotFoundError('git unavailable')):
            with self.assertRaises(FileNotFoundError):preview(self.root,self.source,'missing-git')
        self.assertFalse((self.root/'workdir/builds/missing-git/sprite-preview/result.json').exists())


if __name__=='__main__':unittest.main()
