"""Actual-byte viewer boundaries with a fake client; no board or tunnel."""
import base64
from http.client import HTTPConnection
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.host.client import RejectedCommand
from n2m.live_viewer import FRAME_DOTS, MAX_STEP_FRAMES, Latest, advance, capture_loop, server, PAGE
from fpga_viewer import png_writer, Stop
from n2m.viewer_buttons import Buttons, enqueue, enqueue_mode, history

BUILD = 'ab'*16

class Clock:
    value = 0
    def __call__(self): return self.value
    def wait(self, seconds): self.value += seconds
    def is_set(self): return False

class Fake:
    def __init__(self, clock, fault=None):
        self.clock,self.fault = clock,fault
        self.uncertain = False
        self.sequence = 0
        self.state = abi.STATE_PAUSED
        self.events = []
        self.count = 0
        self.mask = 0
        self.dot = 0
        self.stepped_masks = []
    def identify(self):
        self.events.append('identify')
        return {'abi':1,'build_id':BUILD if self.fault!='identity' else '00'*16}
    def read_host(self, address):
        self.events.append(('read',address))
        return {abi.HOST_REG_IMAGE_VALID:1,abi.HOST_REG_INPUT_SOURCE:abi.INPUT_SOURCE_UART,
                abi.HOST_REG_INPUT_EFFECTIVE:self.mask,abi.HOST_REG_STATE:self.state}[address]
    def write_host(self, address, value):
        self.events.append(('write',address,value))
        if address==abi.HOST_REG_INPUT:self.mask=value
    def control(self, action):
        self.events.append(action)
        assert action in ('RUN','HALT')
        self.state = abi.STATE_RUNNING if action=='RUN' else abi.STATE_PAUSED
    def run_dots(self, count):
        self.events.append(('run_dots',count))
        assert self.state==abi.STATE_PAUSED
        self.stepped_masks.append(self.mask)  # What the core observes while dots run.
        executed = count//2 if self.fault=='short' else count
        self.dot += executed
        return {'dot':self.dot,'executed':executed,
                'reason':abi.WIRE_RUN_DOTS_COUNT if executed==count else abi.WIRE_RUN_DOTS_STOPPED}

    def snapshot(self):
        self.events.append('snapshot')
        assert self.state in (abi.STATE_RUNNING,abi.STATE_PAUSED)
        self.count += 1
        self.clock.value += .25
        if self.fault=='uncertain':
            self.uncertain=True
            raise RuntimeError('fake uncertainty')
        if self.fault=='rejected': raise RejectedCommand('SNAPSHOT',1)
        seq = 1 if self.fault=='duplicate' else self.count
        self.events.append('READ_FRAME_COMPLETE')
        return {'size':5760,'epoch':3,'seq':seq,'dot':seq*70224},bytes([0xe4])*5760


class FakeCamera:
    def __init__(self, clock, fault=None):
        self.clock,self.fault = clock,fault
        self.count = 0
        self.started = self.closed = False
    def start(self):
        self.started=True
        if self.fault=='start':raise RuntimeError('camera failed to start')
    def read(self):
        if self.fault=='read':raise TimeoutError('camera frame stalled')
        self.count+=1;self.clock.value+=.1
        seq = 1 if self.fault=='duplicate' else self.count
        return {'kind':'camera','seq':seq},b'camera-jpeg-'+bytes([seq])
    def close(self):self.closed=True


class ViewerTests(unittest.TestCase):
    def run_loop(self,fault=None,seconds=4):
        clock=Clock();clock.value=0
        client=Fake(clock,fault);latest=Latest(clock=clock)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            result=capture_loop(client,latest,out,png_writer,expected_build=BUILD,stop=clock,
                                clock=clock,wait=clock.wait,seconds=seconds,interval=2)
            png=(out/'capture-1.png').read_bytes() if (out/'capture-1.png').exists() else None
        return result,client,latest,png

    def test_actual_native_pixels_running_captures_and_cleanup(self):
        result,client,latest,png=self.run_loop()
        self.assertEqual((result['status'],result['capture_count']),('PASS',2))
        self.assertEqual(result['cleanup'],{'verified':True,'state':abi.STATE_PAUSED,'input_effective':0})
        self.assertEqual(client.events.count('RUN'),1)
        self.assertEqual(client.events.count('HALT'),1)
        self.assertEqual([x for x in client.events if isinstance(x,tuple) and x[0]=='write'],[('write',abi.HOST_REG_INPUT,0)])
        self.assertEqual(struct.unpack('>IIBBBBB',png[16:29]),(160,144,8,2,0,0,0))
        offset=8;compressed=b''
        while offset<len(png):
            count=int.from_bytes(png[offset:offset+4],'big');kind=png[offset+4:offset+8]
            if kind==b'IDAT':compressed+=png[offset+8:offset+8+count]
            offset+=12+count
        raw=zlib.decompress(compressed)
        expected=b'\0'+bytes([255]*3+[170]*3+[85]*3+[0]*3)*40
        self.assertEqual(raw,expected*144)
        self.assertEqual(latest.read()[0]['state'],'STOPPED')
        self.assertEqual(latest.read()[0]['core_state'],'PAUSED')

    def test_uncertainty_no_cleanup_traffic_and_identity_no_control(self):
        result,client,_,_=self.run_loop('uncertain')
        self.assertFalse(result['cleanup']['verified'])
        self.assertEqual(client.events[-1],'snapshot')
        result,client,_,_=self.run_loop('identity')
        self.assertEqual(client.events,['identify'])
        self.assertEqual(result['status'],'FAIL')

    def test_camera_only_advances_without_a_uart_client_or_controls(self):
        clock=Clock();clock.value=0;camera=FakeCamera(clock);latest=Latest(clock=clock)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            result=capture_loop(None,latest,out,png_writer,expected_build=None,stop=clock,
                                clock=clock,wait=clock.wait,seconds=4,interval=2,camera=camera)
            self.assertFalse((out/'capture-1.2bpp').exists())
            self.assertEqual((out/'capture-1.jpg').read_bytes(),b'camera-jpeg-\1')
            self.assertFalse((out/'capture-1.png').exists())
        self.assertEqual(result['status'],'PASS')
        self.assertGreaterEqual(result['capture_count'],39)
        self.assertEqual((result['image_source'],result['controls_enabled']),('camera',False))
        self.assertEqual(result['cleanup'],{'verified':True,'reason':'camera stopped; UART not opened'})
        self.assertTrue(result['released'])
        self.assertTrue(camera.started and camera.closed)
        status=latest.read()[0]
        self.assertEqual((status['image_source'],status['controls_enabled'],status['source']['kind']),
                         ('camera',False,'camera'))
        self.assertIn(b'Camera view only | UART controls disabled',PAGE)
        self.assertIn(b'physical camera MJPEG frame',PAGE)
        self.assertIn(b"frame.src='/camera.mjpg'",PAGE)

    def test_camera_display_with_uart_controls_keeps_preflight_and_release(self):
        clock=Clock();clock.value=0;camera=FakeCamera(clock);client=Fake(clock);latest=Latest(clock=clock)
        with tempfile.TemporaryDirectory() as folder:
            result=capture_loop(client,latest,Path(folder),png_writer,expected_build=BUILD,stop=clock,
                                clock=clock,wait=clock.wait,seconds=4,interval=2,camera=camera)
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['controls_enabled'])
        self.assertEqual(client.events.count('snapshot'),0)
        self.assertIn('identify',client.events)
        self.assertEqual(result['cleanup'],{'verified':True,'state':abi.STATE_PAUSED,'input_effective':0})
        self.assertEqual([event for event in client.events if event == 'HALT' or
                          isinstance(event,tuple) and event[:2] == ('write',abi.HOST_REG_INPUT)],
                         ['HALT',('write',abi.HOST_REG_INPUT,0)])

    def test_camera_failure_is_retained_and_closes_source(self):
        for fault,stage,error in (('start','camera-start','RuntimeError'),('read','capture','TimeoutError'),
                                  ('duplicate','capture','SourceStale')):
            clock=Clock();clock.value=0;camera=FakeCamera(clock,fault);latest=Latest(clock=clock)
            with tempfile.TemporaryDirectory() as folder:
                result=capture_loop(None,latest,Path(folder),png_writer,expected_build=None,stop=clock,
                                    clock=clock,wait=clock.wait,seconds=4,interval=2,camera=camera)
            self.assertEqual((result['status'],result['stage'],result['error_class']),('FAIL',stage,error))
            self.assertTrue(camera.closed)

    def test_rejections_bounded_duplicate_never_refreshes(self):
        result,client,latest,_=self.run_loop('rejected',10)
        self.assertEqual(client.count,2)
        self.assertEqual(result['capture_count'],0)
        self.assertEqual(result['status'],'FAIL')
        result,client,latest,_=self.run_loop('duplicate')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['capture_count'],1)
        self.assertEqual(latest.read()[0]['sequence'],1)

    def test_freshness_ages_and_history_is_bounded(self):
        clock=Clock();clock.value=0
        latest=Latest(clock=clock)
        latest.publish(b'png',{'epoch':1,'seq':1,'dot':1},.1)
        clock.value=6
        self.assertEqual(latest.read()[0]['state'],'STALE')
        latest.mark('ERROR','capture rejected')
        self.assertEqual(latest.read()[0]['age_seconds'],6)
        result,*_=self.run_loop(seconds=100)
        self.assertEqual(result['capture_count'],50)
        self.assertEqual(len(result['captures']),32)
        self.assertIn(b'age_seconds',PAGE)
        self.assertIn(b'OFFLINE / STALE',PAGE)

    def test_auth_every_read_no_control_and_loopback_only(self):
        latest=Latest();latest.publish(b'actualpng',{'epoch':1,'seq':1,'dot':1},.1)
        http=server(latest,'testuser','x'*40)
        thread=threading.Thread(target=http.serve_forever);thread.start()
        auth={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode()}
        def request(path,headers=None,method='GET'):
            client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
            client.request(method,path,headers=headers or {})
            response=client.getresponse();data=response.read();code=response.status;headers=dict(response.getheaders());client.close()
            return code,data,headers
        try:
            self.assertEqual(http.server_address[0],'127.0.0.1')
            for path in ('/','/status.json','/frame.png','/camera.mjpg','/file','/control'):
                self.assertEqual(request(path)[0],401)
            self.assertEqual(request('/frame.png',auth)[:2],(200,b'actualpng'))
            old=json.loads(request('/status.json',auth)[1])
            latest.publish(b'newpng',{'epoch':1,'seq':2,'dot':2},.1)
            self.assertEqual(request('/frame.png?v='+str(old['sequence']),auth)[0],409)
            self.assertEqual(request('/frame.png?v=2',auth)[:2],(200,b'newpng'))
            self.assertEqual(request('/file',auth)[0],404)
            self.assertEqual(request('/control',auth,'POST')[0],405)
            self.assertEqual(request('/frame.png',auth)[2]['Cache-Control'],'no-store, max-age=0')
        finally:
            http.shutdown();http.server_close();thread.join()

    def test_camera_mjpeg_is_authenticated_and_delivers_without_status_polling(self):
        latest=Latest()
        http=server(latest,'testuser','x'*40,camera_stream=True)
        thread=threading.Thread(target=http.serve_forever);thread.start()
        auth={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode()}
        unauth=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
        unauth.request('GET','/camera.mjpg')
        denied=unauth.getresponse();self.assertEqual(denied.status,401);denied.read();unauth.close()
        client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
        client.request('GET','/camera.mjpg',headers=auth)
        response=client.getresponse()
        try:
            self.assertEqual(response.status,200)
            self.assertEqual(response.getheader('Content-Type'),
                             'multipart/x-mixed-replace; boundary=n2m-camera-frame')
            for sequence,image in ((1,b'jpeg-one'),(2,b'jpeg-two')):
                latest.publish(image,{'kind':'camera','seq':sequence},.01)
                self.assertEqual(response.readline(),b'--n2m-camera-frame\r\n')
                self.assertEqual(response.readline(),b'Content-Type: image/jpeg\r\n')
                self.assertEqual(response.readline(),f'Content-Length: {len(image)}\r\n'.encode())
                self.assertEqual(response.readline(),b'\r\n')
                self.assertEqual(response.read(len(image)),image)
                self.assertEqual(response.read(2),b'\r\n')
            latest.mark('STOPPED')
            self.assertEqual(response.readline(),b'--n2m-camera-frame--\r\n')
        finally:
            response.close();client.close()
            latest.mark('STOPPED')
            http.shutdown();http.server_close();thread.join()

    def test_phone_input_auth_origin_body_and_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);(out/'service.json').write_text('{}')
            origin='https://example.test'
            http=server(Latest(),'testuser','x'*40,input_origin=origin,
                        submit=lambda mask,ms:enqueue(out,mask,ms),command_history=lambda:history(out))
            thread=threading.Thread(target=http.serve_forever);thread.start()
            headers={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode(),
                     'Origin':origin,'Content-Type':'application/json','X-Viewer-Input':'tap'}
            def request(body=b'{"button":"Right"}',override=None,method='POST',path='/input'):
                h=dict(headers);h.update(override or {})
                h={k:v for k,v in h.items() if v is not None}
                client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
                client.request(method,path,body=body,headers=h)
                r=client.getresponse();data=r.read();code=r.status;client.close();return code,data
            try:
                self.assertEqual(request(override={'Authorization':None})[0],401)
                for h in ({'Origin':None},{'Origin':'https://evil.test'},{'X-Viewer-Input':None}):
                    self.assertEqual(request(override=h)[0],403)
                self.assertEqual(request(override={'Content-Type':'text/plain'})[0],415)
                self.assertEqual(request(b'x'*65)[0],413)
                for body in (b'{}',b'bad',b'{"button":"RESET"}',b'{"button":"Right","mask":255}'):
                    self.assertEqual(request(body)[0],400)
                self.assertEqual(request(method='GET')[0],404)
                self.assertFalse((out/'inbox').exists())
                for index in range(1,17):
                    code,data=request();self.assertEqual(code,202)
                    self.assertEqual(json.loads(data)['id'],index)
                self.assertEqual(request()[0],409)
                self.assertEqual(request(b'',override={'Authorization':None},method='GET',path='/status.json')[0],401)
                commands=json.loads(request(b'',method='GET',path='/status.json')[1])['commands']
                self.assertEqual([r['id'] for r in commands],list(range(16,0,-1)))
                self.assertTrue(all(r['state']=='QUEUED' for r in commands))
                records=[json.loads(p.read_text()) for p in (out/'inbox').glob('*.json')]
                self.assertTrue(all(r['mask']==abi.BUTTON_RIGHT and r['milliseconds']==134 for r in records))
                self.assertIn(b"['Up','Left','Right','Down','A','B','Start','Select']",PAGE)
            finally:
                http.shutdown();http.server_close();thread.join()

class ButtonQueueTests(unittest.TestCase):
    def runtime(self, folder):
        out=Path(folder);(out/'service.json').write_text('{}')
        return out

    def test_fifo_capacity_invalid_and_claimed_never_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder)
            for value in (0,256,True):
                with self.assertRaises(ValueError):enqueue(out,value,134)
            for duration in (0,1001,True):
                with self.assertRaises(ValueError):enqueue(out,1,duration)
            ids=[enqueue(out,1,134) for _ in range(16)]
            self.assertEqual(ids,list(range(1,17)))
            with self.assertRaises(ValueError):enqueue(out,1,134)
            first=out/'inbox'/f'{1:020d}.json'
            first.rename(first.with_suffix('.claimed'))
            clock=Clock();clock.value=0;client=Fake(clock)
            receipt=Buttons(out).one(client,clock,clock=clock,wait=clock.wait)
            self.assertEqual(receipt['id'],2)
            self.assertTrue(first.with_suffix('.claimed').exists())
            self.assertTrue(receipt['released'])
            self.assertEqual(client.mask,0)

    def test_frozen_batch_before_capture_and_release_each(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue(out,2,1000)
            clock=Clock();clock.value=0;client=Fake(clock)
            r=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                           stop=clock,seconds=4,interval=2,clock=clock,wait=clock.wait,buttons=Buttons(out))
            self.assertEqual(r['status'],'PASS')
            self.assertEqual([x['id'] for x in r['inputs']],[1,2])
            relevant=[x for x in client.events if x in ('snapshot','READ_FRAME_COMPLETE') or isinstance(x,tuple) and x[0]=='write']
            self.assertEqual(relevant,[
                ('write',abi.HOST_REG_INPUT,1),('write',abi.HOST_REG_INPUT,0),
                ('write',abi.HOST_REG_INPUT,2),('write',abi.HOST_REG_INPUT,0),
                'snapshot','READ_FRAME_COMPLETE','snapshot','READ_FRAME_COMPLETE',
                ('write',abi.HOST_REG_INPUT,0)])

    def test_invalid_record_no_input_and_stop_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            path=next((out/'inbox').glob('*.json'));path.write_text('{"opcode":"RESET"}')
            clock=Clock();clock.value=0;client=Fake(clock)
            receipt=Buttons(out).one(client,clock,clock=clock,wait=clock.wait)
            self.assertEqual(receipt['status'],'REJECTED');self.assertEqual(client.events,[])
            enqueue(out,1,134)
            stop=threading.Event()
            receipt=Buttons(out).one(client,stop,clock=clock,wait=lambda _:stop.set())
            self.assertEqual(receipt['status'],'CANCELLED');self.assertTrue(receipt['released']);self.assertEqual(client.mask,0)
            (out/'STOP').write_text('stop')
            with self.assertRaises(ValueError):enqueue(out,1,134)

    def test_arrival_during_batch_waits_until_next_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            clock=Clock();clock.value=0;client=Fake(clock);published=False
            def wait(seconds):
                nonlocal published
                if not published:
                    enqueue(out,2,134);published=True
                clock.wait(seconds)
            capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                         stop=clock,seconds=4,interval=2,clock=clock,wait=wait,buttons=Buttons(out))
            events=client.events
            self.assertLess(events.index(('write',abi.HOST_REG_INPUT,1)),events.index('snapshot'))
            self.assertGreater(events.index(('write',abi.HOST_REG_INPUT,2)),events.index('READ_FRAME_COMPLETE'))

    def test_history_transitions_retention_and_newest_first(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);buttons=Buttons(out);clock=Clock();clock.value=0;client=Fake(clock)
            for index in range(1,61):
                self.assertEqual(enqueue(out,1,1),index)
                self.assertEqual(history(out)[0]['state'],'QUEUED')
                def wait(seconds):
                    self.assertEqual(history(out)[0]['state'],'EXECUTING')
                    self.assertEqual(client.mask,1)
                    clock.wait(seconds)
                buttons.one(client,clock,clock=clock,wait=wait)
                row=history(out)[0]
                self.assertEqual(row['state'],'RETIRED')
                self.assertTrue(row['released']);self.assertEqual(client.mask,0)
                # Free-run: the milliseconds applied, and no step report is attached.
                self.assertEqual(row['milliseconds'],1);self.assertNotIn('step',row)
                self.assertLessEqual(row['queued_at'],row['started_at'])
                self.assertLessEqual(row['started_at'],row['completed_at'])
            pending=[enqueue(out,2,134) for _ in range(16)]
            rows=history(out)
            self.assertEqual(len(rows),66)
            self.assertEqual([r['id'] for r in rows],list(range(76,10,-1)))
            self.assertEqual({r['id'] for r in rows if r['state']=='QUEUED'},set(pending))
            buttons.close()
            self.assertTrue(all(r['state'] not in ('QUEUED','EXECUTING') for r in history(out)))
            self.assertEqual(history(out)[0]['state'],'CANCELLED')

    def test_history_admission_failure_rolls_back_and_late_queue_cannot_regress(self):
        from unittest.mock import patch
        import n2m.viewer_buttons as module
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder)
            with patch.object(module,'merge_history',side_effect=OSError('history unavailable')):
                with self.assertRaises(OSError):enqueue(out,1,134)
            self.assertFalse(list((out/'inbox').glob('*.json')))
            self.assertFalse(history(out))
            index=enqueue(out,1,134);buttons=Buttons(out)
            buttons.update(index,'EXECUTING',started_at='observed')
            buttons.update(index,'QUEUED',queued_at='late')
            self.assertEqual(history(out)[0]['state'],'EXECUTING')

    def test_release_and_history_failures_never_retire(self):
        from unittest.mock import patch
        import n2m.viewer_buttons as module
        class ReleaseFails(Fake):
            def write_host(self,address,value):
                if value==0:raise RuntimeError('release rejected')
                super().write_host(address,value)
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);clock=Clock();clock.value=0
            with self.assertRaises(RuntimeError):Buttons(out).one(ReleaseFails(clock),clock,clock=clock,wait=clock.wait)
            self.assertEqual(history(out)[0]['state'],'FAILED')
            self.assertFalse(history(out)[0]['released'])
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);clock=Clock();clock.value=0;client=Fake(clock)
            real_merge=module.merge_history
            def fail_terminal(out,changes):
                if any(r['state']=='RETIRED' for r in changes):raise OSError('terminal history unavailable')
                return real_merge(out,changes)
            latest=Latest(clock=clock)
            with patch.object(module,'merge_history',fail_terminal):
                r=capture_loop(client,latest,out,png_writer,expected_build=BUILD,
                               stop=clock,seconds=4,clock=clock,wait=clock.wait,buttons=Buttons(out))
            self.assertEqual(r['status'],'FAIL');self.assertTrue(r['cleanup']['verified'])
            self.assertEqual(client.mask,0);self.assertEqual(latest.read()[0]['state'],'ERROR')
            self.assertNotEqual(history(out)[0]['state'],'RETIRED')

    def test_batch_enumeration_holds_producer_lock(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            original=Path.glob
            def checked(path,pattern):
                if path==out/'inbox':
                    self.assertTrue((path/'producer.lock').exists())
                    with self.assertRaises(FileExistsError):enqueue(out,2,134)
                return original(path,pattern)
            with patch.object(Path,'glob',checked):
                self.assertEqual(len(Buttons(out).batch()),1)
            self.assertEqual(enqueue(out,2,134),2)

    def test_shutdown_closes_admission_and_cancels_pending(self):
        from unittest.mock import patch
        import n2m.viewer_buttons as module
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue(out,2,134)
            cancelled=Buttons(out).close()
            self.assertEqual([r['id'] for r in cancelled],[1,2])
            self.assertTrue(all(r['status']=='CANCELLED' for r in cancelled))
            self.assertFalse(list((out/'inbox').glob('*.json')))
            with self.assertRaises(ValueError):enqueue(out,1,134)
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);real_open=module.os.open
            def stop_before_lock(*args,**kwargs):
                (out/'STOP').write_text('stop')
                return real_open(*args,**kwargs)
            with patch.object(module.os,'open',stop_before_lock):
                with self.assertRaises(ValueError):enqueue(out,1,134)
            self.assertFalse(list((out/'inbox').glob('*.json')))

    def test_operational_supervisor_selects_lease_and_shares_unique_tag(self):
        from unittest.mock import MagicMock,patch
        import fpga_viewer as viewer
        from n2m.fixture_preflight import fixture_imports
        with fixture_imports(viewer.ROOT):
            sys.path.insert(0,str(viewer.ROOT/'src/dv/springtrail'))
            import endurance
            self.assertEqual(Path(endurance.__file__).resolve(),viewer.ROOT/'src/dv/springtrail/endurance.py')
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);tags=[]
                for seconds,cap in [(3600,3630),(30,60)]:
                    tree=MagicMock();tree.__enter__.return_value=tree
                    tree.process.returncode=0
                    with patch.object(viewer,'ROOT',root),patch('n2m.process_tree.Tree',return_value=tree) as launch:
                        self.assertEqual(viewer.main(['--credentials','private.json','--expected-build-id',BUILD,'--seconds',str(seconds)]),0)
                    command=launch.call_args.args[0]
                    tag=command[command.index('--tag')+1];tags.append(tag)
                    self.assertIn('--worker',command)
                    record=json.loads((root/'workdir/builds'/tag/'viewer-budget/budget.json').read_text())
                    self.assertEqual(record['cap_seconds'],cap)
                    self.assertEqual(record['command'],command)
                    tree.process.wait.assert_called_once_with(timeout=cap-12)
                self.assertNotEqual(*tags)
                from n2m.test_budget import WALL_DEFAULT
                self.assertEqual(WALL_DEFAULT,300)
                (root/'workdir/builds/used/live-viewer').mkdir(parents=True)
                with patch.object(viewer,'ROOT',root),self.assertRaises(SystemExit):
                    viewer.main(['--tag','used','--credentials','private.json','--expected-build-id',BUILD])

    def test_camera_cli_is_view_only_unless_uart_controls_are_explicit(self):
        from unittest.mock import MagicMock,patch
        from contextlib import redirect_stderr
        import fpga_viewer as viewer
        from n2m.fixture_preflight import fixture_imports
        import io
        invalid = [
            ['--credentials','private.json','--camera-source','windows-directshow','--expected-build-id',BUILD],
            ['--credentials','private.json','--camera-source','windows-directshow','--uart-port','COM92'],
            ['--credentials','private.json','--camera-source','windows-directshow','--step-frames','1'],
            ['--credentials','private.json','--camera-source','windows-directshow','--camera-uart-controls'],
            ['--credentials','private.json','--camera-uart-controls','--expected-build-id',BUILD],
        ]
        for command in invalid:
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):viewer.main(command)
        private='PRIVATE_CAMERA_SELECTOR'
        tree=MagicMock();tree.__enter__.return_value=tree;tree.process.returncode=0
        with fixture_imports(viewer.ROOT):
            sys.path.insert(0,str(viewer.ROOT/'src/dv/springtrail'))
            import endurance  # noqa: F401
            with tempfile.TemporaryDirectory() as folder,patch.object(viewer,'ROOT',Path(folder)),\
                 patch.dict('os.environ',{'N2M_VIEWER_CAMERA_DEVICE':private},clear=False),\
                 patch('n2m.process_tree.Tree',return_value=tree) as launch:
                self.assertEqual(viewer.main(['--credentials','private.json','--camera-source',
                                              'windows-directshow','--seconds','30']),0)
        command=launch.call_args.args[0]
        self.assertIn('windows-directshow',command)
        self.assertNotIn(private,str(command))

    def test_camera_only_runtime_refuses_local_queue_without_an_inbox_item(self):
        from contextlib import redirect_stderr,redirect_stdout
        from unittest.mock import patch
        import fpga_viewer as viewer
        import io
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            runtime=root/'workdir/builds/cameraonly/live-viewer'
            runtime.mkdir(parents=True)
            (runtime/'service.json').write_text(json.dumps({
                'image_source':'camera','controls_enabled':False}))
            with patch.object(viewer,'ROOT',root),redirect_stderr(io.StringIO()),\
                 self.assertRaises(SystemExit):
                viewer.main(['--tag','cameraonly','--queue-mask','1'])
            self.assertFalse((runtime/'inbox').exists())

            controlled=root/'workdir/builds/cameracontrol/live-viewer'
            controlled.mkdir(parents=True)
            (controlled/'service.json').write_text(json.dumps({
                'image_source':'camera','controls_enabled':True}))
            with patch.object(viewer,'ROOT',root),redirect_stdout(io.StringIO()):
                self.assertEqual(viewer.main(['--tag','cameracontrol','--queue-mask','1']),0)
            self.assertEqual(len(list((controlled/'inbox').glob('*.json'))),1)

    def test_lease_deadline_interrupts_batch_wait(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            with patch('fpga_viewer.time.monotonic',return_value=10):
                stop=Stop(Path(folder)/'STOP',1)
                self.assertFalse(stop.is_set())
            with patch('fpga_viewer.time.monotonic',return_value=11):
                self.assertTrue(stop.is_set())
                self.assertTrue(stop.wait(1))

    def test_stop_file_interrupts_wait(self):
        import time
        with tempfile.TemporaryDirectory() as folder:
            stop=Stop(Path(folder)/'STOP')
            timer=threading.Timer(.03,stop.path.touch);timer.start()
            started=time.monotonic()
            self.assertTrue(stop.wait(1))
            self.assertLess(time.monotonic()-started,.3)
            timer.join()

    def test_uncertain_press_stops_capture_without_further_traffic(self):
        class Broken(Fake):
            def write_host(self,address,value):
                super().write_host(address,value)
                if value:
                    self.uncertain=True
                    raise RuntimeError('uncertain input')
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            clock=Clock();clock.value=0;client=Broken(clock)
            r=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                           stop=clock,seconds=4,clock=clock,wait=clock.wait,buttons=Buttons(out))
            self.assertEqual(r['status'],'FAIL');self.assertFalse(r['cleanup']['verified'])
            self.assertEqual(client.events[-1],('write',abi.HOST_REG_INPUT,1))
            self.assertEqual(client.count,0)
            self.assertEqual(history(out)[0]['state'],'UNCERTAIN')
            self.assertFalse(list((out/'inbox').glob('*.json')))

class SteppedModeTests(unittest.TestCase):
    """Mode is viewer policy over existing host commands; no new UART opcode."""

    def runtime(self, folder):
        out=Path(folder);(out/'service.json').write_text('{}')
        return out

    def loop(self, out, *, fault=None, step_frames=1, seconds=4):
        clock=Clock();clock.value=0;client=Fake(clock,fault);latest=Latest(clock=clock)
        result=capture_loop(client,latest,out,png_writer,expected_build=BUILD,stop=clock,
                            clock=clock,wait=clock.wait,seconds=seconds,interval=2,
                            buttons=Buttons(out),step_frames=step_frames)
        return result,client,latest

    def test_free_run_default_sends_no_run_dots(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            result,client,latest=self.loop(out)
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['mode'],'free-run')
            self.assertNotIn('step',result)
            self.assertFalse([x for x in client.events if x[0]=='run_dots'])
            self.assertEqual(client.events.count('HALT'),1)  # shutdown only
            self.assertEqual(latest.read()[0]['step_frames'],1)

    def test_stepped_order_is_batch_presses_then_step_then_one_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue_mode(out,'stepped')
            result,client,latest=self.loop(out)
            self.assertEqual(result['status'],'PASS')
            relevant=[x for x in client.events
                      if x in ('snapshot','READ_FRAME_COMPLETE','HALT','RUN')
                      or isinstance(x,tuple) and x[0] in ('write','run_dots')]
            self.assertEqual(relevant,[
                'RUN',
                ('write',abi.HOST_REG_INPUT,1),('write',abi.HOST_REG_INPUT,0),
                'HALT',('run_dots',FRAME_DOTS),'snapshot','READ_FRAME_COMPLETE',
                ('run_dots',FRAME_DOTS),'snapshot','READ_FRAME_COMPLETE',
                'HALT',('write',abi.HOST_REG_INPUT,0)])
            self.assertEqual(result['mode'],'stepped')
            self.assertEqual(result['cleanup'],{'verified':True,'state':abi.STATE_PAUSED,'input_effective':0})

    def test_step_reports_whole_frames_executed_and_completed_dot(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            result,client,latest=self.loop(out,step_frames=3)
            self.assertEqual([x for x in client.events if x[0]=='run_dots'],
                             [('run_dots',FRAME_DOTS)]*6)
            step=result['step']
            self.assertEqual(step['frames'],3)
            self.assertEqual(step['requested_dots'],3*FRAME_DOTS)
            self.assertEqual(step['executed_dots'],3*FRAME_DOTS)
            self.assertEqual(step['short_by_dots'],0)
            self.assertEqual(step['completed_dot'],6*FRAME_DOTS)
            status=latest.read()[0]
            self.assertEqual((status['mode'],status['step_frames']),('stepped',3))
            self.assertEqual(result['captures'][-1]['step'],step)
            self.assertEqual(result['captures'][-1]['core_state'],'PAUSED')

    def test_short_step_is_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            result,client,latest=self.loop(out,fault='short',step_frames=2)
            step=result['step']
            self.assertEqual(step['requested_dots'],2*FRAME_DOTS)
            self.assertEqual(step['executed_dots'],FRAME_DOTS//2)
            self.assertEqual(step['short_by_dots'],2*FRAME_DOTS-FRAME_DOTS//2)
            self.assertEqual(step['reason'],abi.WIRE_RUN_DOTS_STOPPED)
            status=latest.read()[0]
            self.assertEqual(status['reason'],'step executed %d of %d dots'%(FRAME_DOTS//2,2*FRAME_DOTS))
            self.assertIn(b'SHORT by ',PAGE)
            # A shortfall ends that step instead of asking for the missing dots.
            self.assertEqual(len([x for x in client.events if x[0]=='run_dots']),2)

    def test_switching_back_to_free_run_resumes_and_stops_stepping(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            clock=Clock();clock.value=0;client=Fake(clock);buttons=Buttons(out);switched=False
            def wait(seconds):
                nonlocal switched
                if not switched and buttons.mode=='stepped':
                    enqueue_mode(out,'free-run');switched=True
                clock.wait(seconds)
            result=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                                stop=clock,seconds=6,interval=2,clock=clock,wait=wait,buttons=buttons)
            self.assertEqual(result['mode'],'free-run')
            self.assertEqual(client.events.count('RUN'),2)
            resumed=len(client.events)-1-client.events[::-1].index('RUN')
            self.assertTrue(all(i<resumed for i,x in enumerate(client.events) if x[0]=='run_dots'))
            self.assertEqual(client.state,abi.STATE_PAUSED)
            self.assertEqual(client.mask,0)

    def test_mode_change_records_history_without_uart_or_held_key(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);index=enqueue_mode(out,'stepped')
            result,client,latest=self.loop(out)
            rows={row['id']:row for row in history(out)}
            self.assertEqual(rows[index]['mode'],'stepped')
            self.assertEqual(rows[index]['state'],'RETIRED')
            self.assertTrue(rows[index]['released'])
            self.assertLessEqual(rows[index]['queued_at'],rows[index]['started_at'])
            self.assertEqual(rows[1]['state'],'RETIRED')
            self.assertTrue(rows[1]['released'])
            self.assertEqual(client.mask,0)
            self.assertFalse(client.uncertain)
            self.assertEqual([r['id'] for r in result['inputs']],[1,2])

    def test_mode_change_cannot_skip_an_in_flight_release(self):
        class ReleaseFails(Fake):
            def write_host(self,address,value):
                if value==0:raise RuntimeError('release rejected')
                super().write_host(address,value)
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue_mode(out,'stepped')
            clock=Clock();clock.value=0;buttons=Buttons(out)
            capture_loop(ReleaseFails(clock),Latest(clock=clock),out,png_writer,
                         expected_build=BUILD,stop=clock,seconds=4,interval=2,
                         clock=clock,wait=clock.wait,buttons=buttons)
            rows={row['id']:row for row in history(out)}
            self.assertEqual(rows[1]['state'],'FAILED')
            self.assertEqual(rows[2]['state'],'QUEUED')
            self.assertEqual(buttons.mode,'free-run')

    def test_invalid_modes_and_step_sizes_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder)
            for mode in ('turbo','','stepped ',1,None,True):
                with self.assertRaises(ValueError):enqueue_mode(out,mode)
            self.assertFalse(list((out/'inbox').glob('*.json')))
            clock=Clock();clock.value=0
            for frames in (0,-1,MAX_STEP_FRAMES+1,True,1.0):
                with self.assertRaises(ValueError):
                    capture_loop(Fake(clock),Latest(clock=clock),out,png_writer,
                                 expected_build=BUILD,stop=clock,clock=clock,
                                 wait=clock.wait,step_frames=frames)

    def test_mode_route_needs_the_same_authentication_as_input(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder)
            origin='https://example.test'
            http=server(Latest(),'testuser','x'*40,input_origin=origin,
                        submit=lambda mask,ms:enqueue(out,mask,ms),
                        submit_mode=lambda mode:enqueue_mode(out,mode),
                        command_history=lambda:history(out))
            thread=threading.Thread(target=http.serve_forever);thread.start()
            headers={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode(),
                     'Origin':origin,'Content-Type':'application/json','X-Viewer-Input':'tap'}
            def request(body=b'{"mode":"stepped"}',override=None):
                h=dict(headers);h.update(override or {})
                h={k:v for k,v in h.items() if v is not None}
                client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
                client.request('POST','/input',body=body,headers=h)
                r=client.getresponse();data=r.read();code=r.status;client.close();return code,data
            try:
                self.assertEqual(request(override={'Authorization':None})[0],401)
                for h in ({'Origin':None},{'Origin':'https://evil.test'},{'X-Viewer-Input':None}):
                    self.assertEqual(request(override=h)[0],403)
                self.assertEqual(request(override={'Content-Type':'text/plain'})[0],415)
                for body in (b'{"mode":"turbo"}',b'{"mode":"stepped","button":"A"}',
                             b'{"mode":1}',b'{"mode":null}'):
                    self.assertEqual(request(body)[0],400)
                self.assertFalse(list((out/'inbox').glob('*.json')))
                code,data=request()
                self.assertEqual((code,json.loads(data)['id']),(202,1))
                self.assertEqual(history(out)[0]['mode'],'stepped')
                self.assertIn(b"for(const mode of ['free-run','stepped'])",PAGE)
                self.assertIn(b'not a real-time proof',PAGE)
            finally:
                http.shutdown();http.server_close();thread.join()

    def test_press_while_already_stepped_is_held_across_its_step(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            clock=Clock();clock.value=0;client=Fake(clock);buttons=Buttons(out);queued=False
            def wait(seconds):
                nonlocal queued
                if not queued and buttons.mode=='stepped':
                    enqueue(out,abi.BUTTON_RIGHT,134);queued=True
                clock.wait(seconds)
            result=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                                stop=clock,seconds=6,interval=2,clock=clock,wait=wait,buttons=buttons)
            self.assertEqual(result['status'],'PASS')
            # The core must see the press while dots run, not only in a register write.
            self.assertEqual(client.stepped_masks,[0,abi.BUTTON_RIGHT,0])
            relevant=[x for x in client.events
                      if x in ('snapshot','READ_FRAME_COMPLETE','HALT','RUN')
                      or isinstance(x,tuple) and x[0] in ('write','run_dots')]
            self.assertEqual(relevant,[
                'RUN','HALT',('run_dots',FRAME_DOTS),'snapshot','READ_FRAME_COMPLETE',
                ('write',abi.HOST_REG_INPUT,abi.BUTTON_RIGHT),('run_dots',FRAME_DOTS),
                ('write',abi.HOST_REG_INPUT,0),'snapshot','READ_FRAME_COMPLETE',
                ('run_dots',FRAME_DOTS),'snapshot','READ_FRAME_COMPLETE',
                'HALT',('write',abi.HOST_REG_INPUT,0)])
            receipt=result['inputs'][-1]
            self.assertEqual(receipt['step']['executed_dots'],FRAME_DOTS)
            self.assertTrue(receipt['released'])
            self.assertEqual(history(out)[0]['state'],'RETIRED')
            # History (served as /status.json commands) carries the receipt's step
            # report, and the page renders that step instead of the ignored ms.
            self.assertEqual(history(out)[0]['step'],receipt['step'])
            self.assertEqual(history(out)[0]['step']['short_by_dots'],0)
            self.assertIn(b"const held=r.step?'1 step, '+r.step.executed_dots+(r.step.short_by_dots?' of '+r.step.requested_dots:'')+' dots':r.milliseconds+' ms'",PAGE)
            self.assertEqual(client.mask,0)
            self.assertFalse(client.uncertain)
            self.assertEqual(result['captures'][-2]['step']['steps'],1)

    def test_short_stepped_press_history_reports_the_shortfall(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            clock=Clock();clock.value=0;client=Fake(clock,'short');buttons=Buttons(out);queued=False
            def wait(seconds):
                nonlocal queued
                if not queued and buttons.mode=='stepped':
                    enqueue(out,abi.BUTTON_A,134);queued=True
                clock.wait(seconds)
            result=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                                stop=clock,seconds=6,interval=2,clock=clock,wait=wait,buttons=buttons)
            receipt=result['inputs'][-1]
            rows={row['id']:row for row in history(out)}
            row=rows[receipt['id']]
            self.assertEqual(row['state'],'RETIRED')
            self.assertEqual(row['step'],receipt['step'])
            self.assertEqual((row['step']['executed_dots'],row['step']['requested_dots']),(FRAME_DOTS//2,FRAME_DOTS))
            self.assertEqual(row['step']['short_by_dots'],FRAME_DOTS//2)
            self.assertEqual(row['step']['reason'],abi.WIRE_RUN_DOTS_STOPPED)

    def test_every_press_in_a_stepped_batch_gets_its_own_step(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue_mode(out,'stepped')
            clock=Clock();clock.value=0;client=Fake(clock);buttons=Buttons(out);queued=False
            def wait(seconds):
                nonlocal queued
                if not queued and buttons.mode=='stepped':
                    enqueue(out,abi.BUTTON_RIGHT,134);enqueue(out,abi.BUTTON_LEFT,134);queued=True
                clock.wait(seconds)
            result=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                                stop=clock,seconds=6,interval=2,clock=clock,wait=wait,buttons=buttons)
            self.assertEqual(client.stepped_masks,[0,abi.BUTTON_RIGHT,abi.BUTTON_LEFT,0])
            capture=result['captures'][-2]['step']
            self.assertEqual((capture['steps'],capture['frames']),(2,2))
            self.assertEqual(capture['executed_dots'],2*FRAME_DOTS)
            self.assertEqual(capture['short_by_dots'],0)

    def test_advance_splits_the_step_into_bounded_calls(self):
        class Bounded:
            def __init__(self):self.calls=[];self.dot=0
            def run_dots(self,count):
                self.calls.append(count);self.dot+=count
                return {'dot':self.dot,'executed':count,'reason':abi.WIRE_RUN_DOTS_COUNT}
        endpoint=Bounded()
        report=advance(endpoint,3*FRAME_DOTS)
        self.assertTrue(all(count<=abi.WIRE_RUN_DOTS_MAX for count in endpoint.calls))
        self.assertEqual(sum(endpoint.calls),3*FRAME_DOTS)
        self.assertEqual(report['executed_dots'],3*FRAME_DOTS)
        self.assertEqual(report['short_by_dots'],0)


PASSWORD='p'*40
DEVICE={'DeviceID':'COM92','PNPDeviceID':'USB\\VID_1234&PID_5678\\ORIGINAL_FAKE',
        'Status':'OK','ConfigManagerErrorCode':0}


class PreflightDiagnosticTests(unittest.TestCase):
    """A refusal before capture keeps its stage and cause; it sends and clears nothing."""
    def run_worker(self, root, open_session, client=None):
        """Drive the real worker with a fake session opener; no board, no console handlers."""
        import fpga_viewer as viewer
        from contextlib import nullcontext, redirect_stderr, redirect_stdout
        from types import SimpleNamespace
        from unittest.mock import patch
        import io
        (root/'private.json').write_text(json.dumps({'username':'viewuser','password':PASSWORD}))
        tag='preflight'+self._testMethodName[-12:].replace('_','')
        args=SimpleNamespace(tag=tag,credentials=str(root/'private.json'),seconds=2,port=0,input_origin=None,
                             interval=1,step_frames=1,expected_build_id=BUILD,uart_port='COM92',uart_vid=None,
                             uart_pid=None,uart_identity=None)
        out,err=io.StringIO(),io.StringIO()
        with patch.object(viewer,'ROOT',root),patch.object(viewer,'machine_lock',lambda _id:nullcontext()),\
             patch.object(viewer,'session',open_session),patch.object(viewer.signal,'signal'),\
             patch.object(viewer,'session_root',lambda _root:root/'state'),\
             patch.object(viewer,'Client',lambda wire,**_:client or wire),\
             redirect_stdout(out),redirect_stderr(err):
            code=viewer.worker(args)
        folder=root/'workdir/builds'/tag/'live-viewer'
        result=json.loads((folder/'result.json').read_text())
        return code,result,folder,out.getvalue(),err.getvalue()

    def assert_private(self, root, *texts):
        """No credential, private selector or local path in any retained or printed text."""
        for text in texts:
            for secret in (PASSWORD,'viewuser',DEVICE['PNPDeviceID'],str(root)):
                self.assertNotIn(secret,text)

    def test_describe_failure_drops_paths_and_keeps_stage_and_class(self):
        from n2m.live_viewer import describe_failure
        held=FileExistsError(17,'File exists','/home/someone/workdir/host-sessions/abc.lock')
        self.assertEqual(describe_failure('session-open',held),
                         {'stage':'session-open','error_class':'FileExistsError','message':'File exists'})
        record=describe_failure('credentials',ValueError('cannot read C:\\Users\\x\\viewer.json here'))
        self.assertEqual(record['message'],'cannot read here')
        self.assertEqual(describe_failure('capture',RuntimeError('x'*300))['message'],'x'*200)
        self.assertEqual(describe_failure('preflight',OSError())['message'],'')

    def test_camera_only_worker_opens_no_machine_or_uart_lock(self):
        import fpga_viewer as viewer
        from contextlib import redirect_stderr,redirect_stdout
        from types import SimpleNamespace
        from unittest.mock import patch
        import io
        class Camera:
            process=None
            def validate(self):self.validated=True
        camera=Camera()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);private=root/'private.json'
            private.write_text(json.dumps({'username':'viewuser','password':PASSWORD}))
            args=SimpleNamespace(tag='cameraonly',credentials=str(private),seconds=1,port=0,input_origin=None,
                                 interval=1,step_frames=1,expected_build_id=None,uart_port=None,uart_vid=None,
                                 uart_pid=None,uart_identity=None,camera_source='windows-directshow',
                                 camera_uart_controls=False)
            def loop(client,latest,out,png_writer,**kwargs):
                self.assertIsNone(client)
                self.assertIs(kwargs['camera'],camera)
                return {'status':'PASS','stage':'capture','capture_count':2,'seconds':1,
                        'released':True,'cleanup':{'verified':True,'reason':'camera stopped; UART not opened'}}
            fail=lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('UART resource touched'))
            with patch.object(viewer,'ROOT',root),patch.object(viewer,'DirectShowCamera',return_value=camera),\
                 patch.object(viewer,'machine_lock',fail),patch.object(viewer,'session',fail),\
                 patch.object(viewer,'capture_loop',side_effect=loop),patch.object(viewer.signal,'signal'),\
                 patch.dict('os.environ',{'N2M_VIEWER_CAMERA_DEVICE':'PRIVATE_CAMERA_SELECTOR'},clear=False),\
                 redirect_stdout(io.StringIO()) as stdout,redirect_stderr(io.StringIO()) as stderr:
                code=viewer.worker(args)
            result=json.loads((root/'workdir/builds/cameraonly/live-viewer/result.json').read_text())
            service=json.loads((root/'workdir/builds/cameraonly/live-viewer/service.json').read_text())
        self.assertEqual((code,result['status'],result['capture_count']),(0,'PASS',2))
        self.assertTrue(camera.validated)
        self.assertEqual((service['image_source'],service['controls_enabled']),('camera',False))
        self.assertNotIn('PRIVATE_CAMERA_SELECTOR',json.dumps(result)+json.dumps(service)+stdout.getvalue()+stderr.getvalue())

    def test_held_lock_before_client_reports_stage_class_and_no_traffic(self):
        from contextlib import contextmanager
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            @contextmanager
            def held(out,args,state_root):
                raise FileExistsError(17,'File exists',str(root/'host-sessions'/('ab'*32+'.lock')))
                yield
            code,result,out,stdout,stderr=self.run_worker(root,held)
            self.assertEqual((out/'packets.jsonl').read_text(),'')
        self.assertEqual(code,1)
        self.assertEqual((result['status'],result['stage'],result['error_class'],result['message']),
                         ('FAIL','session-open','FileExistsError','File exists'))
        self.assertIn('device lock',result['conflict'])
        self.assertEqual(result['cleanup'],{'verified':False,'reason':'session not opened; no control sent'})
        summary=json.loads(stdout)
        self.assertEqual((summary['status'],summary['stage'],summary['error_class']),('FAIL','session-open','FileExistsError'))
        self.assertFalse(summary['cleanup']['verified'])
        self.assertIn('FAIL at stage session-open: FileExistsError (File exists)',stderr)
        self.assertIn('Cleanup verified: False',stderr)
        self.assert_private(root,json.dumps(result),stdout,stderr)

    def test_stale_lock_is_refused_and_left_in_place_with_no_traffic(self):
        from n2m.doctor import select_uart
        from n2m.host.transport import session
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';state.mkdir()
            key=hashlib.sha256(DEVICE['PNPDeviceID'].casefold().encode()).hexdigest()
            lock=state/(key+'.lock');lock.write_text('pid=999999\n')
            opened=[]
            def real(out,args,state_root):
                return session(out,args,state,discover=lambda folder,args:select_uart([DEVICE],args),
                               opener=lambda port:opened.append(port))
            code,result,out,stdout,stderr=self.run_worker(root,real)
            # The dead owner's lock is reported, never reclaimed by the viewer.
            self.assertEqual(lock.read_text(),'pid=999999\n')
            self.assertEqual(sorted(path.name for path in state.iterdir()),[key+'.lock'])
            self.assertEqual(opened,[])
            self.assertEqual((out/'packets.jsonl').read_text(),'')
            self.assertEqual((code,result['stage'],result['error_class']),(1,'session-open','FileExistsError'))
            self.assertIn('Another session holds this device lock',stderr)
            self.assertFalse(result['cleanup']['verified'])
            self.assert_private(root,json.dumps(result),stdout,stderr)

    def test_uncertain_session_is_refused_and_stays_pending(self):
        from n2m.doctor import select_uart
        from n2m.host.transport import session
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';state.mkdir()
            key=hashlib.sha256(DEVICE['PNPDeviceID'].casefold().encode()).hexdigest()
            journal=state/(key+'.json');journal.write_text(json.dumps({'next_sequence':7,'pending':True}))
            opened=[]
            def real(out,args,state_root):
                return session(out,args,state,discover=lambda folder,args:select_uart([DEVICE],args),
                               opener=lambda port:opened.append(port))
            code,result,out,stdout,stderr=self.run_worker(root,real)
            self.assertEqual(json.loads(journal.read_text()),{'next_sequence':7,'pending':True})
            self.assertFalse((state/(key+'.lock')).exists())
            self.assertEqual(opened,[])
            self.assertEqual((out/'packets.jsonl').read_text(),'')
            self.assertEqual((code,result['stage'],result['error_class']),(1,'session-open','RuntimeError'))
            self.assertIn('uncertain',result['message'])
            self.assertIn('durable session for this device is uncertain',stderr)
            self.assertFalse(result['cleanup']['verified'])
            self.assert_private(root,json.dumps(result),stdout,stderr)

    def test_preflight_exception_after_open_names_its_stage_and_sends_no_control(self):
        from contextlib import contextmanager
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);client=Fake(Clock(),'identity')
            @contextmanager
            def opened(out,args,state_root):
                yield client,0,lambda *_:None,DEVICE
            code,result,out,stdout,stderr=self.run_worker(root,opened,client)
        self.assertEqual(client.events,['identify'])
        self.assertEqual((code,result['status'],result['stage'],result['error_class'],result['message']),
                         (1,'FAIL','preflight','ValueError','build mismatch'))
        self.assertEqual(result['cleanup'],{'verified':False,'reason':'preconditions failed; no control sent'})
        self.assertIn('FAIL at stage preflight: ValueError (build mismatch)',stderr)
        self.assert_private(root,json.dumps(result),stdout,stderr)

    def test_capture_stage_and_page_carry_only_the_error_class(self):
        clock=Clock();client=Fake(clock,'uncertain');latest=Latest(clock=clock)
        with tempfile.TemporaryDirectory() as folder:
            result=capture_loop(client,latest,Path(folder),png_writer,expected_build=BUILD,stop=clock,
                                clock=clock,wait=clock.wait,seconds=4,interval=2)
        self.assertEqual((result['stage'],result['error_class'],result['message']),('capture','RuntimeError','fake uncertainty'))
        status=latest.read()[0]
        self.assertEqual((status['state'],status['reason']),('ERROR','RuntimeError'))
        self.assertNotIn('fake uncertainty',json.dumps(status))

    def test_parent_repeats_the_hidden_worker_verdict(self):
        from unittest.mock import MagicMock,patch
        from contextlib import redirect_stdout
        import io
        import fpga_viewer as viewer
        from n2m.fixture_preflight import fixture_imports
        # main() adds the springtrail path under the patched ROOT; import the real
        # supervisor first, isolated from the v05 fixture's own reference module.
        with fixture_imports(viewer.ROOT),tempfile.TemporaryDirectory() as folder:
            import endurance  # noqa: F401
            root=Path(folder);tag='preflightparent'
            retained={'status':'FAIL','stage':'session-open','error_class':'FileExistsError','message':'File exists',
                      'conflict':'Another session holds this device lock.',
                      'cleanup':{'verified':False,'reason':'session not opened; no control sent'}}
            def launch(*_,**__):
                (root/'workdir/builds'/tag/'live-viewer').mkdir(parents=True)
                (root/'workdir/builds'/tag/'live-viewer/result.json').write_text(json.dumps(retained))
                return tree
            tree=MagicMock();tree.__enter__.return_value=tree
            tree.process.returncode=1
            with patch.object(viewer,'ROOT',root),patch('n2m.process_tree.Tree',side_effect=launch),redirect_stdout(io.StringIO()) as stdout:
                code=viewer.main(['--tag',tag,'--credentials','private.json','--expected-build-id',BUILD,'--seconds','30'])
            self.assertEqual(code,1)
            text=stdout.getvalue()
            self.assertIn('Viewer worker FAIL at stage session-open: FileExistsError (File exists)',text)
            self.assertIn('Another session holds this device lock.',text)
            self.assertIn('Cleanup verified: False; session not opened; no control sent',text)
            tree.process.returncode=0
            with patch.object(viewer,'ROOT',root),patch('n2m.process_tree.Tree',return_value=tree),redirect_stdout(io.StringIO()) as stdout:
                code=viewer.main(['--tag','preflightnone','--credentials','private.json','--expected-build-id',BUILD,'--seconds','30'])
            self.assertEqual(code,0)
            self.assertIn('left no result.json',stdout.getvalue())


if __name__=='__main__':unittest.main()
