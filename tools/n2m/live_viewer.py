"""Read-only HTTP view of serialized actual UART snapshots."""
import base64
import hashlib
import hmac
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import generated_interfaces as abi
from .host.client import RejectedCommand
from .springtrail_play import finish

PAGE = b'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FPGA live view</title><style>body{margin:20px;background:#17191c;color:#eee;font:16px system-ui;text-align:center}img{image-rendering:pixelated;display:block;margin:20px auto;background:#333}p{font-variant-numeric:tabular-nums}small{color:#aeb6c0}</style>
<h1>FPGA live view</h1><p id="state">Connecting</p><img id="frame" alt="Actual FPGA pixels"><small id="detail"></small>
<script>
let last=0,sequence=0;const state=document.querySelector('#state'),frame=document.querySelector('#frame'),detail=document.querySelector('#detail');
function scale(){let n=Math.max(1,Math.floor((innerWidth-40)/160));frame.style.width=(160*n)+'px';frame.style.height=(144*n)+'px'}scale();addEventListener('resize',scale);
async function poll(){try{const r=await fetch('/status.json',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();if(s.sequence&&s.sequence!==sequence){const image=await fetch('/frame.png?v='+s.sequence,{cache:'no-store'});if(!image.ok)throw Error();const url=URL.createObjectURL(await image.blob());const prior=frame.src;frame.src=url;sequence=s.sequence;if(prior.startsWith('blob:'))URL.revokeObjectURL(prior)}last=Date.now();state.textContent=s.state+(s.reason?' - '+s.reason:'');detail.textContent=s.sequence?'Capture '+s.sequence+' | '+s.captured_at+' | age '+s.age_seconds.toFixed(1)+' s | '+s.latency_seconds.toFixed(3)+' s capture | '+s.core_state+' | source '+s.source.seq:'Waiting for actual pixels'}catch(e){state.textContent='OFFLINE / STALE'}setTimeout(poll,1000)}poll();setInterval(()=>{if(Date.now()-last>5000)state.textContent='OFFLINE / STALE'},1000);
</script>'''


class SourceStale(ValueError):
    pass


class Latest:
    def __init__(self, *, clock=time.monotonic, stale_after=5):
        self.clock, self.stale_after = clock, stale_after
        self.lock = threading.Lock()
        self.png = None
        self.when = None
        self.data = {'state':'STARTING','sequence':0}

    def publish(self, png, metadata, latency):
        with self.lock:
            prior = self.data.get('source')
            if prior is not None:
                if metadata['epoch'] != prior['epoch']:
                    raise ValueError('source epoch changed')
                if metadata['seq'] <= prior['seq'] or metadata['dot'] <= prior['dot']:
                    raise SourceStale('source frame did not advance')
            self.png, self.when = bytes(png), self.clock()
            self.data = {'state':'LIVE','sequence':self.data['sequence']+1,
                         'captured_at':datetime.now(timezone.utc).isoformat(),
                         'source':dict(metadata),'latency_seconds':latency,'core_state':'RUNNING',
                         'sha256':hashlib.sha256(png).hexdigest()}

    def mark(self, state, reason=None, core_state=None):
        with self.lock:
            self.data['state'] = state
            if core_state is not None:
                self.data['core_state'] = core_state
            if reason:
                self.data['reason'] = reason

    def read(self):
        with self.lock:
            status = dict(self.data)
            age = None if self.when is None else max(0,self.clock()-self.when)
            status['age_seconds'] = age
            if status['state'] == 'LIVE' and age > self.stale_after:
                status['state'] = 'STALE'
            return status, self.png


def server(latest, username, password, port=0):
    expected = b'Basic ' + base64.b64encode((username+':'+password).encode('utf-8'))
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def log_message(self, *_):
            pass  # Never log headers, credentials, URLs or client addresses.

        def respond(self, code, data=b'', kind='text/plain'):
            self.send_response(code)
            self.send_header('Cache-Control','no-store, max-age=0')
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            if code == 401:
                self.send_header('WWW-Authenticate','Basic realm="FPGA viewer", charset="UTF-8"')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def do_GET(self):
            supplied = self.headers.get('Authorization','').encode('utf-8')
            if not hmac.compare_digest(supplied,expected):
                return self.respond(401)
            if self.command != 'GET':
                return self.respond(405)
            parsed = urlsplit(self.path)
            path = parsed.path
            status,png = latest.read()
            if path == '/':
                return self.respond(200,PAGE,'text/html; charset=utf-8')
            if path == '/status.json':
                return self.respond(200,json.dumps(status).encode(),'application/json')
            if path == '/frame.png':
                query = parse_qs(parsed.query)
                if query and query.get('v') != [str(status['sequence'])]:
                    return self.respond(409)
                return self.respond(200,png,'image/png') if png else self.respond(503)
            return self.respond(404)

        do_POST = do_GET
        do_PUT = do_GET
        do_DELETE = do_GET
        do_HEAD = do_GET
        do_OPTIONS = do_GET
        do_PATCH = do_GET
        do_TRACE = do_GET
        do_CONNECT = do_GET
    class LimitedServer(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 8
        slots = threading.BoundedSemaphore(8)
        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                request.close()
                return
            try:
                super().process_request(request,address)
            except Exception:
                self.slots.release()
                raise
        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request,address)
            finally:
                self.slots.release()
    return LimitedServer(('127.0.0.1',port),Handler)


def capture_loop(client, latest, out, png_writer, *, expected_build, stop,
                 seconds=30, interval=2, clock=time.monotonic, wait=None):
    """No load/reset/step/gameplay; one capture/readback at a time."""
    wait = wait or stop.wait
    result = {'status':'FAIL','captures':[],'capture_count':0}
    started = clock()
    try:
        identity = client.identify()
        if identity['build_id'] != expected_build:
            raise ValueError('build mismatch')
        result['identity'] = identity
        if client.read_host(abi.HOST_REG_IMAGE_VALID) != 1:
            raise ValueError('no valid existing image')
        if client.read_host(abi.HOST_REG_INPUT_SOURCE) != abi.INPUT_SOURCE_UART:
            raise ValueError('UART input authority required')
        if client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) != 0:
            raise ValueError('neutral effective input required')
        state = client.read_host(abi.HOST_REG_STATE)
        if state not in (abi.STATE_PAUSED,abi.STATE_RUNNING):
            raise ValueError('existing image must be paused or running')
        if state == abi.STATE_PAUSED:
            client.control('RUN')
        if client.read_host(abi.HOST_REG_STATE) != abi.STATE_RUNNING:
            raise ValueError('core did not resume')
        failures = 0
        while not stop.is_set() and clock()-started < seconds:
            tick = clock()
            try:
                meta,packed = client.snapshot()
                if meta['size'] != abi.FRAME_BYTES or len(packed) != abi.FRAME_BYTES:
                    raise ValueError('frame size mismatch')
                if client.read_host(abi.HOST_REG_STATE) != abi.STATE_RUNNING:
                    raise ValueError('core stopped during capture')
                png_writer(packed,out/'latest.png')
                png = (out/'latest.png').read_bytes()
                latency = clock()-tick
                latest.publish(png,meta,latency)
                row = dict(latest.read()[0],packed_sha256=hashlib.sha256(packed).hexdigest())
                result['capture_count'] += 1
                result['captures'].append(row)
                result['captures'] = result['captures'][-32:]
                from .records import atomic_json
                atomic_json(out/'latest.json',row)
                if result['capture_count'] <= 2:
                    (out/f"capture-{result['capture_count']}.png").write_bytes(png)
                    (out/f"capture-{result['capture_count']}.2bpp").write_bytes(packed)
                failures = 0
            except RejectedCommand:
                failures += 1
                latest.mark('ERROR','capture rejected')
                if failures >= 2:
                    raise
            if client.uncertain:
                raise RuntimeError('uncertain session')
            wait(max(0,interval-(clock()-tick)))
        if not result['captures'] or failures:
            raise ValueError('capture did not end successfully')
        result['status'] = 'PASS'
    except Exception as error:
        result['reason'] = type(error).__name__
        latest.mark('STALE' if isinstance(error,SourceStale) else 'ERROR',type(error).__name__)
    finally:
        # No cleanup/control traffic after failed identity/preconditions.
        if result.get('identity',{}).get('build_id') == expected_build and 'state' in locals() and state in (abi.STATE_PAUSED,abi.STATE_RUNNING):
            finish(client,result)
        else:
            result['cleanup'] = {'verified':False,'reason':'preconditions failed; no control sent'}
        result['seconds'] = clock()-started
        terminal = 'STOPPED' if result['status']=='PASS' and result.get('released') else ('STALE' if result.get('reason')=='SourceStale' else 'ERROR')
        latest.mark(terminal,core_state='PAUSED' if result.get('released') else 'UNKNOWN')
    return result
