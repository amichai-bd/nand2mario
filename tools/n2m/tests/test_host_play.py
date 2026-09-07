"""Independent packed-image and failure checks for the original host scenario."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.host_play import decode_frame, locate, check_image, PlayFailure


def packed_image(x=64, shade=1):
    # Literal rows: 160 pixels/4 =40 bytes, aligned eight-pixel object.
    data = bytearray(5760)
    for row in range(64, 72):
        data[row * 40 + x // 4:row * 40 + x // 4 + 2] = bytes([shade * 0x55]) * 2
    return bytes(data)


class HostPlayTests(unittest.TestCase):
    def test_five_images_and_little_pixel_order(self):
        for x, shade in ((64,1),(72,3),(72,1),(64,3),(64,1)):
            pixels, identity = decode_frame({'epoch':2,'seq':1,'dot':140000,'size':5760},packed_image(x,shade))
            self.assertEqual(check_image(pixels,(x,64,shade)),(x,64,shade))
            self.assertEqual(identity['sequence'],1)
        mixed=bytearray(packed_image());mixed[0]=0xe4
        pixels,_=decode_frame({'epoch':2,'seq':1,'dot':140000,'size':5760},mixed)
        self.assertEqual(pixels[:4],bytes([0,1,2,3]))

    def test_missing_wrong_and_stale_observations(self):
        meta={'epoch':2,'seq':1,'dot':140000,'size':5760}
        for update in ({'epoch':1},{'seq':0},{'size':5759}):
            with self.assertRaises(PlayFailure):decode_frame(dict(meta,**update),packed_image())
        with self.assertRaisesRegex(PlayFailure,'STALE'):
            decode_frame(meta,packed_image(),{'sequence':1,'dot':140000})
        with self.assertRaisesRegex(PlayFailure,'SIZE'):decode_frame(meta,b'')
        with self.assertRaisesRegex(PlayFailure,'COUNT'):locate(bytes(23040))
        pixels,_=decode_frame(meta,packed_image(64,3))
        with self.assertRaisesRegex(PlayFailure,'PLAY_IMAGE'):check_image(pixels,(72,64,3))
        pixels,_=decode_frame(meta,packed_image(72,3))
        with self.assertRaisesRegex(PlayFailure,'PLAY_IMAGE'):check_image(pixels,(72,64,1))

    def test_complete_loop_decisions_and_abort(self):
        from n2m.host_play import play
        from n2m import generated_interfaces as abi
        class Endpoint:
            def __init__(self):
                self.index=0;self.mask=0;self.masks=[];self.actions=[]
            def identify(self):return {'abi':1}
            def load(self,image):return {'verified_bytes':len(image)}
            def select_input_source(self,source):self.source=source
            def read_host(self,address):return self.source if address==abi.HOST_REG_INPUT_SOURCE else self.mask
            def write_host(self,address,value):
                self.assert_address=address;self.mask=value;self.masks.append(value);return {'dots':100+self.index}
            def control(self,action):self.actions.append(action);return {'dots':1000+self.index}
            def snapshot(self):
                x,shade=[(64,1),(72,3),(72,1),(64,3),(64,1)][self.index]
                self.index+=1
                return {'epoch':7,'seq':self.index,'dot':self.index*150000,'size':5760},packed_image(x,shade)
        endpoint=Endpoint();waits=[];kept=[]
        result=play(endpoint,b'original',waits.append,lambda *args:kept.append(args))
        self.assertEqual(endpoint.masks,[0,1,0,2,0])
        self.assertEqual(endpoint.actions,['RUN','HALT']*5)
        self.assertEqual(waits,[200000,150000,150000,150000,150000])
        self.assertEqual(len(result['observations']),5)
        self.assertEqual(result['observations'][-1]['frame']['epoch'],7)
        endpoint=Endpoint()
        endpoint.snapshot=lambda: ({'epoch':7,'seq':1,'dot':150000,'size':5760},bytes(5760))
        with self.assertRaisesRegex(PlayFailure,'COUNT'):
            play(endpoint,b'original',lambda dots:None,lambda *args:None)
        self.assertEqual(endpoint.masks,[0])

    def test_driver_relative_wait_and_failure_propagation(self):
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tcl unavailable; exercised in local Windows check')
        tcl=tkinter.Tcl()
        tcl.eval(r'''
            set smoke_peer_port 1
            set incoming 0
            set advances 0
            array set signals {simulation_ns 0 dot_count 100000 tx_count 0 tx_busy 0 rx_count 0 rx_done 0}
            proc socket {args} { return play }
            proc fconfigure {args} {}
            proc flush {args} {}
            proc puts {args} {}
            proc gets {channel variable} {
                global incoming
                upvar 1 $variable line
                incr incoming
                if {$incoming==1} {set line "WAIT 150000"} else {set line "FAIL PLAY_IMAGE"}
                return [string length $line]
            }
            proc examine {args} {
                global signals
                return $signals([lindex [split [lindex $args end] /] end])
            }
            proc run {amount units} {
                global advances signals
                if {$amount==100} {incr advances;incr signals(dot_count) 50000;incr signals(simulation_ns) 100000}
            }
        ''')
        driver=(Path(__file__).resolve().parents[3]/'src/dv/host_play/driver.do').read_text()
        with self.assertRaisesRegex(tkinter.TclError,'PLAY_IMAGE'):
            tcl.eval(driver)
        self.assertEqual(int(tcl.getvar('advances')),3)
        self.assertEqual(int(tcl.getvar('signals(dot_count)')),250000)
