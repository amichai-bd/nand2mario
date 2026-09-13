"""Private bounded button FIFO; never a public HTTP or arbitrary UART API."""
import json
import os
from pathlib import Path
import time

from .records import atomic_json
from .springtrail_play import apply_mask

CAPACITY = 16


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
    lock = inbox/'producer.lock'
    # Only successful publication is accepted. A crashed reservation leaves a gap,
    # never an accepted request behind a newer request.
    fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        # Recheck while serialized with close: publication is the admission point.
        if (inbox/'CLOSED').exists() or (out/'STOP').exists() or (out/'result.json').exists():
            raise ValueError('viewer runtime is not accepting requests')
        if len(list(inbox.glob('*.json'))) >= CAPACITY:
            raise ValueError('button queue is full')
        sequence_file = inbox/'sequence'
        index = int(sequence_file.read_text())+1 if sequence_file.exists() else 1
        atomic_json(sequence_file,index)
        record = validate({'id':index,'mask':mask,'milliseconds':milliseconds})
        atomic_json(inbox/f'{index:020d}.json',record)
        return index
    finally:
        os.close(fd)
        lock.unlink()


class Buttons:
    def __init__(self, out):
        self.out = Path(out)
        self.inbox = self.out/'inbox'
        self.inbox.mkdir(exist_ok=True)

    def close(self):
        """Close admission and cancel pending requests without touching UART."""
        # The marker also makes a crashed producer fail closed. A producer already
        # inside the lock may publish; cancellation waits for that publication.
        (self.inbox/'CLOSED').touch()
        lock = self.inbox/'producer.lock'
        deadline = time.monotonic()+2
        while True:
            try:
                fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('button producer lock remains; inspect pending requests manually')
                time.sleep(.01)
        try:
            cancelled = [{'id':int(path.stem),'status':'CANCELLED','released':True}
                         for path in sorted(self.inbox.glob('*.json'))]
            atomic_json(self.out/'input-cancelled.json',cancelled)
            for path in self.inbox.glob('*.json'):
                path.unlink()
            return cancelled
        finally:
            os.close(fd)
            lock.unlink()

    def batch(self):
        """Freeze current published IDs; later arrivals wait for the next cycle."""
        lock = self.inbox/'producer.lock'
        deadline = time.monotonic()+2
        while True:
            try:
                fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('button producer lock remains; inspect manually')
                time.sleep(.01)
        try:
            return sorted(self.inbox.glob('*.json'))[:CAPACITY]
        finally:
            os.close(fd)
            lock.unlink()

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
            claimed.unlink()
            return receipt
        try:
            if stop.is_set():
                receipt['status'] = 'CANCELLED'
                return receipt
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
                atomic_json(self.out/'input-latest.json',receipt)
                claimed.unlink()
