"""Temporarily view UART pixels or a Windows camera; no load or programming.

Use a private credential JSON and explicit reviewed build/device selectors.
Only the local operator can stop the worker; HTTP exposes image/status reads.
Camera-only mode is view-only and opens no UART session. Camera UART controls
are an explicit opt-in and keep the reviewed-build and neutral-release checks.
`--gui` instead opens a local on-screen Game Boy pad: it sends buttons only,
reads no frames and serves no HTTP, because the player watches the board's VGA
output directly.
"""
import argparse
import json
import os
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
from n2m.gui_pad import explain_conflict, pad_loop
from n2m.live_viewer import MAX_STEP_FRAMES, Latest, capture_loop, describe_failure, server
from n2m.records import atomic_json
from n2m.viewer_buttons import Buttons, enqueue, enqueue_mode, history
from n2m.windows_camera import DirectShowCamera


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


def load_credentials(path):
    credential_path = Path(path).resolve()
    if not credential_path.is_file():
        raise ValueError('private credentials file must be initialized before launch')
    credentials = json.loads(credential_path.read_text(encoding='utf-8'))
    if not credentials.get('username') or len(credentials.get('password','')) < 32:
        raise ValueError('high entropy credentials required')
    return credentials


def failure_line(result):
    """One operator line: stage, error class and redacted message; never a secret.

    A refusal names its cleanup outcome so it cannot read as a clean stop.
    """
    line = f"Viewer worker FAIL at stage {result.get('stage','unknown')}: {result.get('error_class') or result.get('reason','unknown')}"
    if result.get('message'):
        line += f" ({result['message']})"
    if result.get('conflict'):
        line += '\n'+result['conflict']
    cleanup = result.get('cleanup') or {}
    return line+f"\nCleanup verified: {cleanup.get('verified',False)}; {cleanup.get('reason','see result.json')}"


def report_worker(path):
    """The hidden worker's retained verdict, said again on the parent's terminal."""
    if not path.is_file():
        return 'Viewer worker left no result.json; see viewer-budget/budget.json under the tag'
    result = json.loads(path.read_text(encoding='utf-8'))
    if result.get('status') == 'PASS':
        return f"Viewer worker PASS: {result.get('capture_count',0)} captures in {result.get('seconds')} s"
    return failure_line(result)


def worker(args):
    out = ROOT/'workdir/builds'/args.tag/'live-viewer'
    out.mkdir(parents=True,exist_ok=False)
    # Until a client exists no session was opened, so cleanup is truthfully "none".
    camera_source = getattr(args,'camera_source',None)
    camera_uart_controls = getattr(args,'camera_uart_controls',False)
    controls = camera_source is None or camera_uart_controls
    result = {'status':'FAIL','stage':'credentials','reason':'preflight not completed',
              'cleanup':{'verified':False,'reason':('session not opened; no control sent'
                         if controls else 'camera not started; UART not opened')}}
    http = buttons = camera = None
    try:
        credentials = load_credentials(args.credentials)
        if camera_source is not None:
            result['stage'] = 'camera-config'
            camera = DirectShowCamera(os.environ.get('N2M_VIEWER_CAMERA_DEVICE',''),
                                      os.environ.get('N2M_VIEWER_FFMPEG') or None)
            camera.validate()
        result['stage'] = 'http-server'
        latest = Latest()
        stop = Stop(out/'STOP',args.seconds)
        signal.signal(signal.SIGINT,lambda *_:stop.event.set())
        signal.signal(signal.SIGTERM,lambda *_:stop.event.set())
        submit = (lambda mask,ms:enqueue(out,mask,ms)) if controls else None
        submit_mode = (lambda mode:enqueue_mode(out,mode)) if controls else None
        command_history = (lambda:history(out)) if controls else None
        http = server(latest,credentials['username'],credentials['password'],args.port,
                      input_origin=args.input_origin,submit=submit,
                      submit_mode=submit_mode,command_history=command_history,
                      camera_stream=camera_source is not None)
        thread = threading.Thread(target=http.serve_forever,daemon=True)
        thread.start()
        atomic_json(out/'service.json',{'port':http.server_port,'bind':'127.0.0.1',
                    'stop_file':str(stop.path),'seconds':args.seconds,
                    'image_source':'camera' if camera_source is not None else 'uart',
                    'controls_enabled':controls})
        if controls:
            selection = SimpleNamespace(uart_port=args.uart_port,uart_vid=args.uart_vid,
                                        uart_pid=args.uart_pid,uart_identity=args.uart_identity,endpoint_restarted=False)
            buttons = Buttons(out)
            result['stage'] = 'machine-lock'
            with machine_lock(1357311510), (out/'packets.jsonl').open('w',encoding='utf-8') as packets:
                def record(row):
                    packets.write(json.dumps(row)+'\n');packets.flush()
                result['stage'] = 'session-open'
                with session(out,selection,session_root(ROOT)) as (wire,sequence,persist,_selected):
                    client = Client(wire,sequence=sequence,persist=persist,record=record)
                    result = capture_loop(client,latest,out,png_writer,expected_build=args.expected_build_id,
                                          stop=stop,seconds=args.seconds,interval=args.interval,buttons=buttons,
                                          step_frames=args.step_frames,camera=camera)
        else:
            result = capture_loop(None,latest,out,png_writer,expected_build=None,
                                  stop=stop,seconds=args.seconds,interval=args.interval,
                                  step_frames=args.step_frames,camera=camera)
    except Exception as error:
        # A refusal before capture keeps its decisive cause: the stage, the error
        # class and a message with no path, device fact or credential in it.
        result.update(describe_failure(result['stage'],error))
        explanation = explain_conflict(error)
        if explanation:
            result['conflict'] = explanation
    finally:
        if buttons is not None:
            try:
                result['cancelled_inputs'] = buttons.close()
            except Exception as error:
                result.update(status='FAIL',queue_close_error=str(error))
        if camera is not None and camera.process is not None:
            try:
                camera.close()
            except Exception as error:
                result.update(status='FAIL',camera_cleanup_error=type(error).__name__)
        atomic_json(out/'result.json',result)
        if http is not None:
            http.shutdown();http.server_close();thread.join(timeout=2)
    print(json.dumps({'status':result['status'],'captures':result.get('capture_count',0),
                      'seconds':result.get('seconds'),'cleanup':result.get('cleanup'),
                      'stage':result.get('stage'),'error_class':result.get('error_class')}))
    if result['status'] != 'PASS':
        print(failure_line(result),file=sys.stderr)
    return 0 if result['status']=='PASS' and result.get('released') else 1


def require_build_id(parser, args):
    if not args.expected_build_id or len(args.expected_build_id)!=32 or any(c not in '0123456789abcdef' for c in args.expected_build_id):
        parser.error('explicit reviewed 32-digit lowercase build ID required')


def gamepad(args):
    """Own one UART session for the on-screen pad; read no frames, serve no HTTP."""
    out = ROOT/'workdir/builds'/args.tag/'gui-pad'
    out.mkdir(parents=True,exist_ok=False)
    print(f'Pad tag {args.tag}; lease {args.seconds}s; results under {out}',flush=True)
    selection = SimpleNamespace(uart_port=args.uart_port,uart_vid=args.uart_vid,
                                uart_pid=args.uart_pid,uart_identity=args.uart_identity,endpoint_restarted=False)
    result = {'status':'FAIL','reason':'session not opened','changes':0,'released':False}
    try:
        with machine_lock(1357311510), (out/'packets.jsonl').open('w',encoding='utf-8') as packets:
            def record(row):
                packets.write(json.dumps(row)+'\n');packets.flush()
            with session(out,selection,session_root(ROOT)) as (wire,sequence,persist,_selected):
                client = Client(wire,sequence=sequence,persist=persist,record=record)
                result = pad_loop(client,expected_build=args.expected_build_id,record=record,seconds=args.seconds)
    except Exception as error:
        # The owner needs the actual cause, above all when someone else holds the board.
        result.update(status='FAIL',reason=type(error).__name__,error=str(error))
        explanation = explain_conflict(error)
        if explanation:
            result['conflict'] = explanation
            print(explanation,file=sys.stderr)
        else:
            print(f'{type(error).__name__}: {error}',file=sys.stderr)
    finally:
        atomic_json(out/'result.json',result)
    print(json.dumps({'status':result['status'],'changes':result.get('changes',0),
                      'released':result.get('released',False),'cleanup':result.get('cleanup')}))
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
    parser.add_argument('--port',type=int,help='viewer HTTP port; default8765')
    parser.add_argument('--gui',action='store_true',help='open a local tkinter Game Boy pad; sends buttons only, reads no frames')
    parser.add_argument('--seconds',type=int,help='session lease; default30 for the viewer and900 for --gui')
    parser.add_argument('--interval',type=float,help='viewer capture interval; default2')
    parser.add_argument('--step-frames',type=int,help='whole 70224-dot frames advanced per capture in stepped mode; default1')
    parser.add_argument('--camera-source',choices=('windows-directshow',),
                        help='show a private Windows camera instead of UART pixels')
    parser.add_argument('--camera-uart-controls',action='store_true',
                        help='with camera display, explicitly open the protected UART control session')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(arguments)
    step_frames_selected = args.step_frames is not None
    viewer_only = {'--interval':args.interval,'--step-frames':args.step_frames,
                   '--credentials':args.credentials,'--init-credentials':args.init_credentials or None,
                   '--input-origin':args.input_origin,'--port':args.port,'--queue-mask':args.queue_mask,
                   '--camera-source':args.camera_source,
                   '--camera-uart-controls':args.camera_uart_controls or None}
    if args.seconds is None:
        args.seconds = 900 if args.gui else 30
    if args.interval is None:
        args.interval = 2
    if args.step_frames is None:
        args.step_frames = 1
    if args.port is None:
        args.port = 8765
    if args.tag is None:
        if args.queue_mask is not None:
            parser.error('running viewer tag required for queue submission')
        args.tag = 'viewer'+uuid.uuid4().hex
        arguments += ['--tag',args.tag]
    if not args.tag.isalnum():
        parser.error('tag must be alphanumeric')
    if args.queue_mask is not None and not args.gui:
        runtime = ROOT/'workdir/builds'/args.tag/'live-viewer'
        try:
            service = json.loads((runtime/'service.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            parser.error('running viewer service required for queue submission')
        if service.get('controls_enabled') is not True:
            parser.error('running viewer has no UART controls')
        index = enqueue(runtime,args.queue_mask,args.press_ms)
        print(json.dumps({'status':'QUEUED','id':index}))
        return 0
    if args.gui:
        refused = sorted(name for name,value in viewer_only.items() if value is not None)
        if refused:
            parser.error('--gui reads no frames, serves no HTTP and queues nothing; it refuses '
                         +', '.join(refused))
        require_build_id(parser,args)
        if not 1 <= args.seconds <= 3600:
            parser.error('seconds1..3600 required')
        if (ROOT/'workdir/builds'/args.tag/'gui-pad').exists():
            parser.error('runtime tag already exists; omit --tag for a fresh session')
        return gamepad(args)
    if not args.credentials:
        parser.error('private credentials path required for initialization or serving')
    if args.init_credentials:
        path = Path(args.credentials)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as stream:
            json.dump({'username':secrets.token_urlsafe(12),'password':secrets.token_urlsafe(32)},stream)
        print('Private credentials initialized; contents not displayed.')
        return 0
    if args.camera_source is None:
        if args.camera_uart_controls:
            parser.error('--camera-uart-controls requires --camera-source')
        require_build_id(parser,args)
    elif args.camera_uart_controls:
        require_build_id(parser,args)
    else:
        private_uart = args.expected_build_id or any((args.uart_port,args.uart_vid,args.uart_pid,args.uart_identity))
        if private_uart:
            parser.error('camera-only mode refuses UART options; add --camera-uart-controls to open UART')
        if step_frames_selected:
            parser.error('camera-only mode has no stepped UART control')
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
    code = supervise(command,args.seconds+30,ROOT/'workdir/builds'/args.tag/'viewer-budget')
    # The worker runs without a console window, so its verdict is repeated here.
    print(report_worker(ROOT/'workdir/builds'/args.tag/'live-viewer/result.json'),flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
