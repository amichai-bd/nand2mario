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
from .viewer_buttons import DEFAULT_MODE, MODES

FRAME_DOTS = 70224  # One whole DMG frame; the step unit in stepped mode.
MAX_STEP_FRAMES = 60

PAGE = b'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FPGA live view</title><style>body{margin:20px;background:#17191c;color:#eee;font:16px system-ui;text-align:center}img{image-rendering:pixelated;display:block;margin:20px auto;background:#333}p{font-variant-numeric:tabular-nums}small{color:#aeb6c0}#commands{text-align:left;font:14px system-ui;padding-left:20px}#commands li{padding:6px}.QUEUED{color:#77baff}.EXECUTING{color:#ffd166}.RETIRED{color:#84df9b}.FAILED,.UNCERTAIN{color:#ff9393}.CANCELLED{color:#aaa}</style>
<h1>FPGA live view</h1><p id="state">Connecting</p><img id="frame" alt="Actual FPGA pixels"><small id="detail"></small><p id="buttons"></p><p id="modes"></p><p id="mode-status"></p><p id="input-status"></p><h2>Commands (newest first)</h2><ol id="commands"></ol>
<script>
let last=0,sequence=0;const state=document.querySelector('#state'),frame=document.querySelector('#frame'),detail=document.querySelector('#detail');
async function send(payload,name){const label=document.querySelector('#input-status');try{const r=await fetch('/input',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Input':'tap'},body:JSON.stringify(payload)});if(!r.ok)throw Error('Queue full, busy, stopped or refused');const result=await r.json();label.textContent='Queued '+name+' #'+result.id}catch(e){label.textContent=e.message}}
function control(target,text,payload){const b=document.createElement('button');b.textContent=text;b.style.cssText='font:20px system-ui;padding:12px;margin:4px';b.onclick=()=>send(payload,text);document.querySelector(target).appendChild(b)}
for(const button of ['Up','Left','Right','Down','A','B','Start','Select'])control('#buttons',button,{button});
for(const mode of ['free-run','stepped'])control('#modes','Mode: '+mode,{mode});
function modeStatus(s){const step=s.step?' | advanced '+s.step.steps+' step(s), '+s.step.executed_dots+' of '+s.step.requested_dots+' dots to dot '+s.step.completed_dot+(s.step.short_by_dots?' | SHORT by '+s.step.short_by_dots+' dots (reason '+s.step.reason+')':''):'';document.querySelector('#mode-status').textContent='Mode '+(s.mode||'unknown')+(s.mode==='stepped'?' | step '+s.step_frames+' frame(s) of 70224 dots'+step+' | not a real-time proof':'')}
function scale(){let n=Math.max(1,Math.floor((innerWidth-40)/160));frame.style.width=(160*n)+'px';frame.style.height=(144*n)+'px'}scale();addEventListener('resize',scale);
function commands(s){const list=document.querySelector('#commands');list.replaceChildren();if(s.commands_error){list.textContent=s.commands_error;return}for(const r of s.commands||[]){const li=document.createElement('li');li.className=r.state;const names=['Right','Left','Up','Down','A','B','Select','Start'].filter((n,i)=>r.mask&(1<<i)).join('+');const held=r.step?'1 step, '+r.step.executed_dots+(r.step.short_by_dots?' of '+r.step.requested_dots:'')+' dots':r.milliseconds+' ms';const what=r.mode?'mode '+r.mode:(names||'mask '+r.mask)+' '+held;li.textContent='#'+r.id+' '+what+' | '+r.state+' | queued '+(r.queued_at||'-')+' | started '+(r.started_at||'-')+' | completed '+(r.completed_at||'-');list.appendChild(li)}}
async function poll(){try{const r=await fetch('/status.json',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();commands(s);modeStatus(s);if(s.sequence&&s.sequence!==sequence){const image=await fetch('/frame.png?v='+s.sequence,{cache:'no-store'});if(!image.ok)throw Error();const url=URL.createObjectURL(await image.blob());const prior=frame.src;frame.src=url;sequence=s.sequence;if(prior.startsWith('blob:'))URL.revokeObjectURL(prior)}last=Date.now();state.textContent=s.state+(s.reason?' - '+s.reason:'');detail.textContent=s.sequence?'Capture '+s.sequence+' | '+s.captured_at+' | age '+s.age_seconds.toFixed(1)+' s | '+s.latency_seconds.toFixed(3)+' s capture | '+s.core_state+' | source '+s.source.seq:'Waiting for actual pixels'}catch(e){state.textContent='OFFLINE / STALE'}setTimeout(poll,1000)}poll();setInterval(()=>{if(Date.now()-last>5000)state.textContent='OFFLINE / STALE'},1000);
</script>'''


class SourceStale(ValueError):
    pass


def describe_failure(stage, error):
    """Stage and error class of a failure, with a message naming no path or secret.

    The retained result and the operator's terminal carry this record. An OSError
    keeps only its strerror, so a held session lock reports 'File exists' and
    never its local path or hashed device key; any other message drops every
    word that looks like a path. Credentials are never part of an exception here.
    """
    message = (error.strerror or '') if isinstance(error,OSError) else str(error)
    words = [word for word in message.split() if '/' not in word and '\\' not in word]
    return {'stage':stage,'error_class':type(error).__name__,'message':' '.join(words)[:200]}


class Latest:
    def __init__(self, *, clock=time.monotonic, stale_after=5):
        self.clock, self.stale_after = clock, stale_after
        self.lock = threading.Lock()
        self.png = None
        self.when = None
        self.data = {'state':'STARTING','sequence':0}
        self.notes = {'mode':DEFAULT_MODE}

    def describe(self, **fields):
        """Sticky status fields, such as the active mode, kept across captures."""
        with self.lock:
            self.notes.update(fields)

    def publish(self, png, metadata, latency, extra=None):
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
            self.data.update(extra or {})

    def mark(self, state, reason=None, core_state=None):
        with self.lock:
            self.data['state'] = state
            if core_state is not None:
                self.data['core_state'] = core_state
            if reason:
                self.data['reason'] = reason

    def read(self):
        with self.lock:
            status = dict(self.data,**self.notes)
            age = None if self.when is None else max(0,self.clock()-self.when)
            status['age_seconds'] = age
            if status['state'] == 'LIVE' and age > self.stale_after:
                status['state'] = 'STALE'
            return status, self.png


def server(latest, username, password, port=0, *, input_origin=None, submit=None,
           submit_mode=None, command_history=None):
    if input_origin is not None:
        origin = urlsplit(input_origin)
        if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:
            raise ValueError('input origin must be an exact HTTPS origin')
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
                if command_history is not None:
                    try:
                        status['commands'] = command_history()
                    except (OSError,ValueError):
                        status['commands_error'] = 'Command history unavailable'
                return self.respond(200,json.dumps(status).encode(),'application/json')
            if path == '/frame.png':
                query = parse_qs(parsed.query)
                if query and query.get('v') != [str(status['sequence'])]:
                    return self.respond(409)
                return self.respond(200,png,'image/png') if png else self.respond(503)
            return self.respond(404)

        def do_POST(self):
            lengths = self.headers.get_all('Content-Length',[])
            size = int(lengths[0]) if len(lengths)==1 and lengths[0].isdigit() else 0
            payload = self.rfile.read(min(size,65)) if size else b''
            supplied = self.headers.get('Authorization','').encode('utf-8')
            if not hmac.compare_digest(supplied,expected):
                return self.respond(401)
            if self.path != '/input' or submit is None:
                return self.respond(405)
            if self.headers.get('Origin') != input_origin or not input_origin or self.headers.get('X-Viewer-Input') != 'tap':
                return self.respond(403)
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                return self.respond(415)
            lengths = self.headers.get_all('Content-Length',[])
            if len(lengths) != 1 or not lengths[0].isdigit():
                return self.respond(411)
            size = int(lengths[0])
            if not 1 <= size <= 64:
                return self.respond(413)
            try:
                record = json.loads(payload)
                masks = {'Right':1,'Left':2,'Up':4,'Down':8,'A':16,'B':32,'Select':64,'Start':128}
                if not isinstance(record,dict):
                    raise ValueError('invalid request')
                # Mode selection shares this route, and so its authentication.
                if set(record) == {'mode'} and submit_mode is not None:
                    if record['mode'] not in MODES:
                        raise ValueError('invalid mode')
                    action = lambda:submit_mode(record['mode'])
                elif set(record) == {'button'} and record['button'] in masks:
                    action = lambda:submit(masks[record['button']],134)
                else:
                    raise ValueError('invalid button')
            except (ValueError,TypeError):
                return self.respond(400)
            try:
                index = action()
            except (ValueError,FileExistsError):
                return self.respond(409,b'Queue full, busy or stopped')
            return self.respond(202,json.dumps({'status':'QUEUED','id':index}).encode(),'application/json')

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


def state_for(mode):
    return abi.STATE_PAUSED if mode=='stepped' else abi.STATE_RUNNING


def advance(client, dots):
    """Execute exactly `dots` emulated dots through bounded RUN_DOTS calls.

    A STOPPED reply ends the step early; the shortfall is returned so the
    viewer can report it rather than pretend the step completed.
    """
    executed, completed, reason = 0, None, abi.WIRE_RUN_DOTS_COUNT
    while executed < dots:
        reply = client.run_dots(min(abi.WIRE_RUN_DOTS_MAX,dots-executed))
        executed += reply['executed']
        completed = reply['dot']
        if reply['reason'] != abi.WIRE_RUN_DOTS_COUNT:
            reason = reply['reason']
            break
    return {'requested_dots':dots,'executed_dots':executed,'completed_dot':completed,
            'reason':reason,'short_by_dots':dots-executed}


def combine(reports, step_frames):
    """One per-capture account of every step this cycle advanced."""
    short = next((report['reason'] for report in reports
                  if report['reason'] != abi.WIRE_RUN_DOTS_COUNT),abi.WIRE_RUN_DOTS_COUNT)
    return {'steps':len(reports),'frames':step_frames*len(reports),
            'requested_dots':sum(report['requested_dots'] for report in reports),
            'executed_dots':sum(report['executed_dots'] for report in reports),
            'completed_dot':reports[-1]['completed_dot'],'reason':short,
            'short_by_dots':sum(report['short_by_dots'] for report in reports)}


def capture_loop(client, latest, out, png_writer, *, expected_build, stop,
                 seconds=30, interval=2, clock=time.monotonic, wait=None, buttons=None,
                 step_frames=1):
    """No load/reset/gameplay; one capture/readback at a time.

    Free-run is the default and lets the board run between captures. Stepped
    mode pauses the core and advances exactly `step_frames` whole frames per
    capture, so it is not evidence of sustained native-rate behavior.
    """
    if type(step_frames) is not int or not 1 <= step_frames <= MAX_STEP_FRAMES:
        raise ValueError('step must be 1..%d whole frames' % MAX_STEP_FRAMES)
    wait = wait or stop.wait
    # `stage` names where a failure happened: identity/preconditions, or capture.
    result = {'status':'FAIL','stage':'preflight','captures':[],'capture_count':0}
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
        active = DEFAULT_MODE
        latest.describe(mode=active,step_frames=step_frames)
        result['mode'] = active
        steps = []

        def sync_mode():
            """Enter the selected mode; RUN_DOTS needs a paused core."""
            nonlocal active
            requested = buttons.mode if buttons is not None else DEFAULT_MODE
            if requested == active:
                return
            client.control('HALT' if requested=='stepped' else 'RUN')
            active = requested
            if client.read_host(abi.HOST_REG_STATE) != state_for(active):
                raise ValueError('core did not enter '+active+' mode')
            result['mode'] = active
            latest.describe(mode=active)

        def hold():
            """Advance the step with the press still applied, or keep wall time."""
            if active != 'stepped':
                return None
            steps.append(advance(client,step_frames*FRAME_DOTS))
            return steps[-1]

        result['stage'] = 'capture'
        while not stop.is_set() and clock()-started < seconds:
            tick = clock()
            steps.clear()
            # A mode selected in an earlier cycle applies before this batch, so a
            # press in stepped mode is held across its own step.
            sync_mode()
            if buttons is not None:
                batch = buttons.batch()
                if batch:
                    latest.mark('PROCESSING INPUTS')
                for path in batch:
                    if stop.is_set():
                        break
                    receipt = buttons.one(client,stop,clock=clock,wait=wait,path=path,hold=hold)
                    result.setdefault('inputs',[]).append(receipt)
                    result['inputs'] = result['inputs'][-32:]
                if stop.is_set():
                    break
            step = None
            try:
                # A mode change inside this batch takes effect after its presses.
                sync_mode()
                expected_state = state_for(active)
                if active == 'stepped' and not steps:
                    steps.append(advance(client,step_frames*FRAME_DOTS))
                if steps:
                    step = combine(steps,step_frames)
                    result['step'] = step
                tick = clock()
                meta,packed = client.snapshot()
                if meta['size'] != abi.FRAME_BYTES or len(packed) != abi.FRAME_BYTES:
                    raise ValueError('frame size mismatch')
                if client.read_host(abi.HOST_REG_STATE) != expected_state:
                    raise ValueError('core stopped during capture')
                png_writer(packed,out/'latest.png')
                png = (out/'latest.png').read_bytes()
                latency = clock()-tick
                extra = {'core_state':'PAUSED' if active=='stepped' else 'RUNNING'}
                latest.publish(png,meta,latency,extra=dict(extra,step=step) if step else extra)
                if step and step['short_by_dots']:
                    # Surfaced with the image it belongs to; never quietly dropped.
                    latest.mark('LIVE','step executed %d of %d dots' % (step['executed_dots'],step['requested_dots']))
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
        result.update(describe_failure(result['stage'],error))
        # The page learns only the class name; the message stays in the result.
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
