"""Temporarily view the already-loaded FPGA image; no load, reset or gameplay.

Use a private credential JSON and explicit reviewed build/device selectors.
Only the local operator can stop the worker; HTTP exposes image/status reads.
"""
import argparse
import json
import secrets
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ci.storage import machine_lock
from n2m.host.client import Client
from n2m.host.transport import session, session_root
from n2m.live_viewer import MAX_STEP_FRAMES, Latest, capture_loop, server
from n2m.records import atomic_json
from n2m.viewer_buttons import Buttons, enqueue, enqueue_mode, history


def png_writer(packed, path):
    sys.path.insert(0,str(ROOT/'src/dv/libbet'))
    try:
        import frame_png
    finally:
        sys.path.pop(0)
    frame_png.write_frame(frame_png.unpack(packed),path)


class Stop:
    def __init__(self, path, seconds=None):
        self.deadline = None if seconds is None else time.monotonic()+seconds
        self.path = path
        self.event = threading.Event()

    def is_set(self):
        return self.event.is_set() or self.path.exists() or (self.deadline is not None and time.monotonic() >= self.deadline)

    def wait(self, seconds):
        deadline = time.monotonic()+seconds
        while not self.is_set():
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return False
            self.event.wait(min(.02,remaining))
        return True


def worker(args):
    out = ROOT/'workdir/builds'/args.tag/'live-viewer'
    out.mkdir(parents=True,exist_ok=False)
    credential_path = Path(args.credentials).resolve()
    if not credential_path.is_file():
        raise ValueError('private credentials file must be initialized before launch')
    credentials = json.loads(credential_path.read_text(encoding='utf-8'))
    if not credentials.get('username') or len(credentials.get('password','')) < 32:
        raise ValueError('high entropy credentials required')
    latest = Latest()
    stop = Stop(out/'STOP',args.seconds)
    signal.signal(signal.SIGINT,lambda *_:stop.event.set())
    signal.signal(signal.SIGTERM,lambda *_:stop.event.set())
    http = server(latest,credentials['username'],credentials['password'],args.port,
                  input_origin=args.input_origin,submit=lambda mask,ms:enqueue(out,mask,ms),
                  submit_mode=lambda mode:enqueue_mode(out,mode),command_history=lambda:history(out))
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    atomic_json(out/'service.json',{'port':http.server_port,'bind':'127.0.0.1','stop_file':str(stop.path),'seconds':args.seconds})
    selection = SimpleNamespace(uart_port=args.uart_port,uart_vid=args.uart_vid,
                                uart_pid=args.uart_pid,uart_identity=args.uart_identity,endpoint_restarted=False)
    result = {'status':'FAIL','reason':'preflight not completed'}
    buttons = Buttons(out)
    try:
        with machine_lock(1357311510), (out/'packets.jsonl').open('w',encoding='utf-8') as packets:
            def record(row):
                packets.write(json.dumps(row)+'\n');packets.flush()
            with session(out,selection,session_root(ROOT)) as (wire,sequence,persist,_selected):
                client = Client(wire,sequence=sequence,persist=persist,record=record)
                result = capture_loop(client,latest,out,png_writer,expected_build=args.expected_build_id,
                                      stop=stop,seconds=args.seconds,interval=args.interval,buttons=buttons,
                                      step_frames=args.step_frames)
    finally:
        try:
            result['cancelled_inputs'] = buttons.close()
        except Exception as error:
            result.update(status='FAIL',queue_close_error=str(error))
        atomic_json(out/'result.json',result)
        http.shutdown();http.server_close();thread.join(timeout=2)
    print(json.dumps({'status':result['status'],'captures':result.get('capture_count',0),
                      'seconds':result.get('seconds'),'cleanup':result.get('cleanup')}))
    return 0 if result['status']=='PASS' and result.get('released') else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',help='unique runtime tag; automatically generated when serving')
    parser.add_argument('--credentials',help='private local JSON; contents are never printed')
    parser.add_argument('--init-credentials',action='store_true')
    parser.add_argument('--queue-mask',type=lambda value:int(value,0),help='publish a local bounded button press; never opens UART')
    parser.add_argument('--press-ms',type=int,default=134)
    parser.add_argument('--expected-build-id')
    for name in ('uart-port','uart-vid','uart-pid','uart-identity'):
        parser.add_argument('--'+name)
    parser.add_argument('--input-origin',help='exact HTTPS browser origin allowed to submit fixed taps')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--interval',type=float,default=2)
    parser.add_argument('--step-frames',type=int,default=1,help='whole 70224-dot frames advanced per capture in stepped mode')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(arguments)
    if args.tag is None:
        if args.queue_mask is not None:
            parser.error('running viewer tag required for queue submission')
        args.tag = 'viewer'+uuid.uuid4().hex
        arguments += ['--tag',args.tag]
    if not args.tag.isalnum():
        parser.error('tag must be alphanumeric')
    if args.queue_mask is not None:
        index = enqueue(ROOT/'workdir/builds'/args.tag/'live-viewer',args.queue_mask,args.press_ms)
        print(json.dumps({'status':'QUEUED','id':index}))
        return 0
    if not args.credentials:
        parser.error('private credentials path required for initialization or serving')
    if args.init_credentials:
        path = Path(args.credentials)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as stream:
            json.dump({'username':secrets.token_urlsafe(12),'password':secrets.token_urlsafe(32)},stream)
        print('Private credentials initialized; contents not displayed.')
        return 0
    if not args.expected_build_id or len(args.expected_build_id)!=32 or any(c not in '0123456789abcdef' for c in args.expected_build_id):
        parser.error('explicit reviewed 32-digit lowercase build ID required')
    if not 1 <= args.seconds <= 3600 or not 1 <= args.interval <= 10 or not 1024 <= args.port <= 65535:
        parser.error('seconds1..3600, interval1..10 and unprivileged port required')
    if not 1 <= args.step_frames <= MAX_STEP_FRAMES:
        parser.error(f'step frames1..{MAX_STEP_FRAMES} required')
    if args.worker:
        return worker(args)
    if (ROOT/'workdir/builds'/args.tag/'live-viewer').exists():
        parser.error('runtime tag already exists; omit --tag for a fresh session')
    command = [sys.executable,str(Path(__file__).resolve()),*arguments,'--worker']
    # Operational lease, not the simulation supervisor's shrink-only ceiling.
    sys.path.insert(0,str(ROOT/'src/dv/springtrail'))
    from endurance import supervise
    print(f'Viewer tag {args.tag}; lease {args.seconds}s; whole cap {args.seconds+30}s',flush=True)
    return supervise(command,args.seconds+30,ROOT/'workdir/builds'/args.tag/'viewer-budget')


if __name__ == '__main__':
    raise SystemExit(main())
