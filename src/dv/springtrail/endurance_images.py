"""Three native captured-frame illustrations; no model pixels or repository archive."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools/wiki'))
from board_frames import indexed_png, unpack

SELECTED = ('origin-title', '000-retry', '000-pause')

def export(out):
    out = Path(out)
    result = json.loads((out/'run/result.json').read_text(encoding='utf-8'))
    assert result['status'] == 'PASS', 'ENDURANCE_IMAGE_RUN'
    rows = {row['name']: row for row in result['samples']}
    images = []
    for name in SELECTED:
        row = rows[name]
        assert row['file'] == name+'.2bpp' and row['checked_pixels'] == 23040, 'ENDURANCE_IMAGE_SOURCE'
        packed = (out/'run'/row['file']).read_bytes()
        digest = hashlib.sha256(packed).hexdigest()
        assert digest == row['sha256'], 'ENDURANCE_IMAGE_HASH'
        png = indexed_png(unpack(packed))
        path = out/(name+'.png')
        path.write_bytes(png)
        images.append(dict(name=name, file=path.name, sha256=hashlib.sha256(png).hexdigest(),
                           packed_sha256=digest, metadata=row['metadata'],
                           rom_sha256=result['rom_sha256'], checked_pixels=23040))
    manifest = dict(source='actual UART snapshot bytes', width=160, height=144,
                    format='PNG indexed 2-bit, four shades', images=images)
    (out/'images.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

def publish(out, gh, pr, *, execute=subprocess.run):
    """Use the supported CLI; an upload failure never becomes publication PASS."""
    out = Path(out)
    manifest = json.loads((out/'images.json').read_text(encoding='utf-8'))
    lines = ['Three native actual UART snapshots; no physical monitor claim.']
    command = [str(gh), 'pr', 'comment', str(pr), '--body-file', str(out/'images.md')]
    for row in manifest['images']:
        path = out/row['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'ENDURANCE_PNG_HASH'
        m = row['metadata']
        lines.append(f"{row['name']}: ROM {row['rom_sha256']}; frame {m['seq']}, dot {m['dot']}, epoch {m['epoch']}; PNG SHA256 {row['sha256']}.\n\n![{row['name']}]({path.name})")
        command.extend(['--attach', str(path)])
    (out/'images.md').write_text('\n\n'.join(lines),encoding='utf-8')
    result = execute(command,cwd=out,text=True,capture_output=True,timeout=120)
    receipt = dict(status='FAIL' if result.returncode else 'UPLOADED_UNVERIFIED', exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    (out/'publication.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    if result.returncode:
        raise RuntimeError('ENDURANCE_ATTACHMENT_UPLOAD')
    # CLI success creates a comment, but callers must read back the attachment
    # URLs and verify downloaded content before recording verified publication.
    return receipt


def verify_publication(out, urls, downloaded):
    """Bind durable GitHub asset links to bytes downloaded through supported access."""
    out = Path(out)
    manifest = json.loads((out/'images.json').read_text(encoding='utf-8'))
    receipt = json.loads((out/'publication.json').read_text(encoding='utf-8'))
    assert receipt['status'] == 'UPLOADED_UNVERIFIED', 'ENDURANCE_UPLOAD_REQUIRED'
    assert len(urls) == len(downloaded) == len(manifest['images']) == 3, 'ENDURANCE_ATTACHMENT_COUNT'
    for row,url,data in zip(manifest['images'],urls,downloaded):
        assert url.startswith('https://github.com/user-attachments/assets/') and '?' not in url, 'ENDURANCE_ATTACHMENT_URL'
        assert hashlib.sha256(data).hexdigest() == row['sha256'], 'ENDURANCE_ATTACHMENT_HASH'
    receipt.update(status='PASS', attachments=[dict(url=u,sha256=r['sha256']) for u,r in zip(urls,manifest['images'])])
    (out/'publication.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt
