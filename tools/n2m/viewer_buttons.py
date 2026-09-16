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
MODES = ('free-run','stepped')
DEFAULT_MODE = MODES[0]


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
    if set(record) not in ({'id','mask','milliseconds'},{'id','mode'}):
        raise ValueError('button record fields')
    if type(record['id']) is not int or record['id'] < 1:
        raise ValueError('button record sequence')
    if 'mode' in record:
        if record['mode'] not in MODES:
            raise ValueError('viewer mode outside the published set')
        return record
    if type(record['mask']) is not int or not 1 <= record['mask'] <= 255:
        raise ValueError('button mask outside1..255')
    if type(record['milliseconds']) is not int or not 1 <= record['milliseconds'] <= 1000:
        raise ValueError('button duration outside1..1000ms')
    return record


def enqueue(out, mask, milliseconds):
    """Publish one bounded press into the shared FIFO."""
    return submit(out,{'mask':mask,'milliseconds':milliseconds})


def enqueue_mode(out, mode):
    """Publish one mode change; it is ordered and retained like a press."""
    return submit(out,{'mode':mode})


def submit(out, fields):
    out = Path(out)
    validate(dict(fields,id=1))
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
        record = validate(dict(fields,id=index))
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
        self.mode = DEFAULT_MODE

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

    def one(self, client, stop, *, clock=time.monotonic, wait=None, path=None, hold=None):
        """Claim once, complete/release before returning to capture.

        `hold` replaces the wall-clock press duration when the caller advances
        emulated time instead; it runs with the mask applied and returns its
        report, or None to keep the wall-clock hold.
        """
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
            if 'mode' in record:
                # Mode selection sends no UART traffic, so it can never leave a
                # key pressed; the batch already released every earlier press.
                self.mode = record['mode']
                receipt['status'] = 'APPLIED'
                return receipt
            pressed = True
            apply_mask(client,record['mask'])
            started = clock()
            # Stepped mode holds the mask across the step, so the core actually
            # observes the press; wall time alone would execute no dots.
            report = None if hold is None else hold()
            if report is None:
                (wait or stop.wait)(record['milliseconds']/1000)
            else:
                receipt['step'] = report
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
                # A stepped press lasted its step, not its milliseconds; history
                # carries the same step report as the receipt so every surface agrees.
                effect = {'step':receipt['step']} if 'step' in receipt else {}
                self.update(record['id'],state,completed_at=timestamp(),released=receipt.get('released',False),**effect)
