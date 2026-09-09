"""Bounded real-ROM route using ordinary Client operations and applied dots."""
import json,math,time,zlib
from pathlib import Path
from n2m import generated_interfaces as abi
from physical_reference import LCD,PERIOD,predict,visible_boundary,expected_snapshot

DOT_HZ=4194304


def run(client,rom,folder,log,expected_build,expected_epoch=2):
    folder=Path(folder);events=[];checks=[];dot=0;mask=0;completed=False
    def note(kind,**values):log(dict(kind=kind,**values))
    def pause_visible():
        nonlocal dot
        dot=client.control('HALT')['dot']
        for _ in range(6):
            if visible_boundary(dot):return
            client.control('RUN');time.sleep(.002)
            dot=client.control('HALT')['dot']
        raise AssertionError('PHYSICAL_VISIBLE_PAUSE')
    def apply(value):
        nonlocal mask
        assert visible_boundary(dot),'PHYSICAL_INPUT_WINDOW'
        actual=client.control('INPUT',value)['dot']
        assert actual==dot and (not events or actual>events[-1][0]),'PHYSICAL_APPLIED_DOT'
        events.append((actual,value));mask=value
        note('applied',dot=actual,buttons=value)
    def current():
        assert visible_boundary(dot),'PHYSICAL_CURRENT_PHASE'
        state,playing=predict((dot-LCD)//PERIOD,events)
        assert playing and not state.fell,'PHYSICAL_ROUTE_STATE'
        return state
    def advance(target,direction):
        for _ in range(8):
            remaining=(target-current().x//16)*direction
            if remaining<=0:return
            count=math.ceil(remaining/2)
            client.control('RUN')
            time.sleep(max(.001,count*PERIOD/DOT_HZ-.008))
            pause_visible()
        raise AssertionError('PHYSICAL_ROUTE_PROGRESS')
    def capture(name,low,high,*,title=False,camera=None):
        metadata,packed=client.snapshot()
        state,want=expected_snapshot(metadata,events,epoch)
        assert low<=state.x//16<=high and not state.fell,'PHYSICAL_CHECKPOINT_RANGE'
        if camera is not None:assert camera[0]<=state.camera<=camera[1],'PHYSICAL_CAMERA_RANGE'
        assert predict(metadata['seq'],events)[1] != title,'PHYSICAL_CHECKPOINT_MODE'
        assert not checks or metadata['seq']>checks[-1]['metadata']['seq'],'PHYSICAL_FRAME_PROGRESS'
        pixels=bytes((value>>shift)&3 for value in packed for shift in (0,2,4,6))
        assert len(pixels)==23040,'PHYSICAL_FRAME_SIZE'
        mismatches=sum(a!=b for a,b in zip(pixels,want))
        (folder/f'{name}.2bpp').write_bytes(packed)
        assert not mismatches,f'PHYSICAL_FRAME_PIXELS checkpoint={name} mismatches={mismatches}'
        assert client.read_host(abi.HOST_REG_INPUT_SOURCE)==0,'PHYSICAL_INPUT_SOURCE'
        assert client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)==mask,'PHYSICAL_EFFECTIVE_INPUT'
        record=dict(name=name,metadata=metadata,state=state.__dict__,pixels=23040,
                    crc32=f'{zlib.crc32(pixels):08x}',mismatches=mismatches)
        checks.append(record);note('checkpoint',**record)
    try:
        identity=client.identify()
        assert identity['build_id']==expected_build,'PHYSICAL_BUILD_ID'
        assert client.read_host(abi.HOST_REG_STATE)==abi.STATE_PAUSED,'PHYSICAL_INITIAL_STATE'
        loaded=client.load(rom)
        # The reviewed fresh-program gate followed by LOAD_BEGIN/END supplies
        # epoch2; the first public snapshot must independently confirm it.
        epoch=expected_epoch
        assert client.read_host(abi.HOST_REG_INPUT_SOURCE)==0 and client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)==0,'PHYSICAL_INITIAL_INPUT'
        client.control('RUN');time.sleep(.1);pause_visible()
        capture('title',24,24,title=True,camera=(0,0))
        apply(128);client.control('RUN');time.sleep(.06);pause_visible()
        capture('first-world',24,24,camera=(0,0))
        apply(33)
        advance(68,1);capture('before-camera',60,76,camera=(0,4))
        advance(88,1);capture('entering-column',80,96,camera=(8,24))
        advance(148,1);capture('first-gap-approach',140,156)
        apply(49);advance(240,1);capture('first-gap-cleared',232,248)
        apply(33);advance(316,1);capture('before-scroll-wrap',308,324,camera=(236,252))
        advance(340,1);capture('after-scroll-wrap',332,348,camera=(260,276))
        apply(49);advance(432,1);capture('second-gap-cleared',424,440)
        apply(33);advance(532,1);capture('third-gap-approach',524,540)
        apply(49);advance(624,1);capture('third-gap-cleared',616,632)
        apply(33);advance(692,1);capture('camera-clamp',684,700,camera=(608,608))
        advance(760,1)
        client.control('RUN');time.sleep(.04);pause_visible()
        capture('right-world-limit',760,760,camera=(608,608))
        apply(34);advance(624,-1);capture('reverse-third-gap',616,632)
        apply(50);advance(528,-1);capture('reverse-third-cleared',520,536)
        apply(34);advance(432,-1);capture('reverse-second-gap',424,440)
        apply(50);advance(336,-1);capture('reverse-second-cleared',328,344)
        apply(34);advance(316,-1);capture('reverse-scroll-wrap',308,324,camera=(236,252))
        advance(240,-1);capture('reverse-first-gap',232,248)
        apply(50);advance(144,-1);capture('reverse-first-cleared',136,152)
        apply(34);advance(64,-1);capture('camera-left-clamp',56,72,camera=(0,0))
        advance(0,-1)
        client.control('RUN');time.sleep(.04);pause_visible()
        capture('left-world-limit',0,0,camera=(0,0))
        apply(0)
        assert client.read_host(abi.HOST_REG_STATE)==abi.STATE_PAUSED and not client.uncertain,'PHYSICAL_FINAL_STATE'
        assert client.read_host(abi.HOST_REG_INPUT)==0 and client.read_host(abi.HOST_REG_INPUT_EFFECTIVE)==0,'PHYSICAL_FINAL_INPUT'
        result=dict(status='PASS',identity=identity,load=loaded,epoch=epoch,events=events,
                    checkpoints=checks,final_dot=dot,final_input=0,certain=True)
        (folder/'route.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        completed=True
        return result
    finally:
        if not completed and not client.uncertain:
            client.control('HALT');client.control('INPUT',0)
