"""Bounded button FIFO and truthful operator history; no arbitrary UART API."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from .records import atomic_json, published_bytes
from .springtrail_play import apply_mask

CAPACITY = 16
ACTIVE = {'QUEUED','EXECUTING'}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def producer(inbox, wait=False):
    lock = inbox/'producer.lock'
    deadline = time.monotonic()+2
    while True:
        try:
            fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            break
        except FileExistsError:
            if not wait:
                raise
            if time.monotonic() >= deadline:
                raise RuntimeError('button producer lock remains; inspect manually')
            time.sleep(.01)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def history(out):
    path = Path(out)/'input-history.json'
    return json.loads(published_bytes(path)) if path.exists() else []


def merge_history(out, changes):
    """Caller holds producer lock; never regress execution to admission."""
    rows = {row['id']:row for row in history(out)}
    for change in changes:
        row = rows.get(change['id'],{})
        if row.get('state') not in (None,'QUEUED') and change['state']=='QUEUED':
            continue
        row.update(change)
        rows[change['id']] = row
    ordered = sorted(rows.values(),key=lambda row:row['id'],reverse=True)
    terminal = [row for row in ordered if row['state'] not in ACTIVE][:50]
    active = [row for row in ordered if row['state'] in ACTIVE]
    atomic_json(Path(out)/'input-history.json',sorted(active+terminal,key=lambda row:row['id'],reverse=True))


def validate(record):
    if set(record) != {'id','mask','milliseconds'}:
        raise ValueError('button record fields')
    if type(record['id']) is not int or record['id'] < 1:
        raise ValueError('button record sequence')
    if type(record['mask']) is not int or not 1 <= record['mask'] <= 255:
        raise ValueError('button mask outside1..255')
    if type(record['milliseconds']) is not int or not 1 <= record['milliseconds'] <= 1000:
        raise ValueError('button duration outside1..1000ms')
    return record


def enqueue(out, mask, milliseconds):
    out = Path(out)
    validate({'id':1,'mask':mask,'milliseconds':milliseconds})
    if not (out/'service.json').is_file() or (out/'STOP').exists() or (out/'result.json').exists():
        raise ValueError('viewer runtime is not accepting requests')
    inbox = out/'inbox'
    inbox.mkdir(exist_ok=True)
    with producer(inbox):
        if (inbox/'CLOSED').exists() or (out/'STOP').exists() or (out/'result.json').exists():
            raise ValueError('viewer runtime is not accepting requests')
        if len(list(inbox.glob('*.json'))) >= CAPACITY:
            raise ValueError('button queue is full')
        sequence_file = inbox/'sequence'
        index = int(sequence_file.read_text())+1 if sequence_file.exists() else 1
        atomic_json(sequence_file,index)
        record = validate({'id':index,'mask':mask,'milliseconds':milliseconds})
        path = inbox/f'{index:020d}.json'
        atomic_json(path,record)
        try:
            merge_history(out,[dict(record,state='QUEUED',queued_at=timestamp())])
        except Exception:
            path.unlink()  # Not accepted; batch cannot claim while this lock is held.
            raise
        return index


class Buttons:
    def __init__(self, out):
        self.out = Path(out)
        self.inbox = self.out/'inbox'
        self.inbox.mkdir(exist_ok=True)

    def update(self, index, state, **fields):
        with producer(self.inbox,wait=True):
            merge_history(self.out,[dict(fields,id=int(index),state=state)])

    def close(self):
        """Close admission and cancel pending requests without touching UART."""
        (self.inbox/'CLOSED').touch()
        with producer(self.inbox,wait=True):
            pending = sorted(self.inbox.glob('*.json'))
            cancelled = [{'id':int(path.stem),'status':'CANCELLED','released':True} for path in pending]
            merge_history(self.out,[dict(id=row['id'],state='CANCELLED',completed_at=timestamp()) for row in cancelled])
            atomic_json(self.out/'input-cancelled.json',cancelled)
            for path in pending:
                path.unlink()
            return cancelled

    def batch(self):
        """Freeze current published IDs; later arrivals wait for the next cycle."""
        with producer(self.inbox,wait=True):
            return sorted(self.inbox.glob('*.json'))[:CAPACITY]

    def one(self, client, stop, *, clock=time.monotonic, wait=None, path=None):
        """Claim once, complete/release before returning to capture."""
        if path is None:
            pending = self.batch()
            if not pending:
                return None
            path = pending[0]
        claimed = path.with_suffix('.claimed')
        path.rename(claimed)
        receipt = {'id':path.stem,'status':'REJECTED'}
        pressed = False
        try:
            if claimed.is_symlink() or claimed.stat().st_size > 512:
                raise ValueError('invalid private button file')
            record = validate(json.loads(claimed.read_text(encoding='utf-8')))
            if record['id'] != int(path.stem):
                raise ValueError('button filename sequence mismatch')
            receipt.update(record)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as error:
            receipt['reason'] = type(error).__name__
            atomic_json(self.out/'input-latest.json',receipt)
            self.update(path.stem,'FAILED',completed_at=timestamp(),reason=receipt['reason'])
            claimed.unlink()
            return receipt
        try:
            if stop.is_set():
                receipt['status'] = 'CANCELLED'
                return receipt
            self.update(record['id'],'EXECUTING',started_at=timestamp())
            pressed = True
            apply_mask(client,record['mask'])
            started = clock()
            (wait or stop.wait)(record['milliseconds']/1000)
            receipt['held_seconds'] = clock()-started
            receipt['status'] = 'CANCELLED' if stop.is_set() else 'APPLIED'
            return receipt
        except Exception as error:
            receipt['status'] = 'FAILED'
            receipt['reason'] = type(error).__name__
            raise
        finally:
            # Safety precedes persistence: history failure can never skip release.
            try:
                if pressed and not client.uncertain:
                    apply_mask(client,0)
                    receipt['released'] = True
                else:
                    receipt['released'] = not pressed
            except Exception as error:
                receipt.update(status='FAILED',released=False,reason=type(error).__name__)
                raise
            finally:
                state = 'UNCERTAIN' if client.uncertain else ('RETIRED' if receipt['status']=='APPLIED' and receipt.get('released') else receipt['status'])
                atomic_json(self.out/'input-latest.json',receipt)
                claimed.unlink()
                self.update(record['id'],state,completed_at=timestamp(),released=receipt.get('released',False))
