"""Independent key edges and real Client packets; no keyboard or UART opened."""
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.host.client import Client, UncertainCompletion
from n2m.host.keyboard import run
from n2m.host.command import run as command
from n2m.host.console import Console
from n2m.interface_codec import decode_packet, encode_packet, pack_record, unpack_record
from n2m.tests.test_host import Endpoint


class Wire(Endpoint):
    def __init__(self, defect=None):
        super().__init__()
        self.valid = 1
        self.owner = 0
        self.fault = defect

    def write(self, packet):
        header, payload = decode_packet(packet)
        if header['command'] == abi.COMMAND_READ_HOST:
            address = unpack_record('read_host', payload)['address']
            if address in (abi.HOST_REG_INPUT_SOURCE, abi.HOST_REG_INPUT_EFFECTIVE):
                value = self.owner if address == abi.HOST_REG_INPUT_SOURCE else self.buttons
                self.requests.append(('READ_HOST', payload, header['seq']))
                self.pending.extend(encode_packet(header['seq'], header['command'], pack_record('word', {'value': value}), kind=abi.WIRE_RESPONSE))
                return len(packet)
        if header['command'] == abi.COMMAND_INPUT:
            self.defect = self.fault
        return super().write(packet)


class Events:
    def __init__(self, *events):
        self.events = iter(events)

    def next_event(self):
        event = next(self.events)
        if isinstance(event, BaseException):
            raise event
        return event


def key(code, down=True, modifiers=0):
    return ('key', code, down, modifiers)


def masks(wire):
    return [unpack_record('input', raw)['buttons'] for name, raw, _ in wire.requests if name == 'INPUT']


class KeyboardTests(unittest.TestCase):
    def test_all_keys_chords_repeats_and_partial_release(self):
        # Literal expected bits are independent of the production mapping.
        for code, expected in ((0x27,1),(0x25,2),(0x26,4),(0x28,8),(0x5a,16),(0x58,32),(0xa1,64),(0x0d,128)):
            wire = Wire()
            result = run(Client(wire), Events(key(code), key(code), key(code,False), key(0x1b)))
            self.assertEqual(masks(wire), [expected,0,0])
            self.assertTrue(result['released'])
        wire = Wire()
        run(Client(wire), Events(key(0x27),key(0x5a),key(0x25),key(0x5a,False),key(0x27,False),key(0x25,False),key(0x1b)))
        self.assertEqual(masks(wire), [1,17,19,3,2,0,0])

    def test_unmapped_modifiers_and_focus_drop_queued_keys(self):
        wire = Wire()
        run(Client(wire), Events(key(0x41),key(0x58,True,0x08),key(0x5a),key(0x5a,False,0x08),('focus-lost',),key(0x27)))
        self.assertEqual(masks(wire), [16,0,0])
        wire = Wire()
        run(Client(wire), Events(key(0x27),key(0x43,True,0x08),key(0x58)))
        self.assertEqual(masks(wire), [1,0])

    def test_console_failure_releases_but_transport_failure_does_not(self):
        wire = Wire()
        client = Client(wire)
        with self.assertRaisesRegex(OSError, 'console read'):
            run(client, Events(key(0x27),OSError('console read')))
        self.assertEqual(masks(wire), [1,0])
        self.assertFalse(client.uncertain)
        for fault in ('short-write','timeout','sequence','length','crc'):
            wire = Wire(fault)
            persisted = []
            client = Client(wire,persist=lambda seq,pending:persisted.append((seq,pending)))
            with self.assertRaises(UncertainCompletion):
                run(client,Events(key(0x27),key(0x1b)))
            self.assertEqual(masks(wire),[1])
            self.assertTrue(client.uncertain)
            self.assertTrue(persisted[-1][1])

    def test_preflight_and_release_failure(self):
        for field,value in (('valid',0),('owner',1),('buttons',4)):
            wire=Wire();setattr(wire,field,value)
            with self.assertRaises(ValueError):run(Client(wire),Events(key(0x27)))
            self.assertEqual(masks(wire),[])
        wire=Wire('timeout');client=Client(wire)
        with self.assertRaises(UncertainCompletion):run(client,Events(key(0x1b)))
        self.assertEqual(masks(wire),[0]);self.assertTrue(client.uncertain)

    def test_command_console_gate_before_session_and_build_gate(self):
        root=Path(__file__).resolve().parents[3]
        args=SimpleNamespace(action='keyboard',json=False,endpoint_restarted=False,expected_build_id='1'*32)
        with tempfile.TemporaryDirectory(dir=root/'workdir') as temp:
            with patch('n2m.host.console.Console',side_effect=RuntimeError('unsupported console')), patch('n2m.host.command.session') as opened:
                result=command(root,Path(temp),args,{})
                self.assertEqual(result['status'],'FAIL');opened.assert_not_called()
            wire=Wire()
            with patch('n2m.host.console.Console',return_value=nullcontext(Events(key(0x1b)))), patch('ci.storage.machine_lock',return_value=nullcontext()), patch('n2m.host.command.session',return_value=nullcontext((wire,0,lambda *_:None,{}))):
                result=command(root,Path(temp),args,{})
                self.assertEqual(result['status'],'FAIL');self.assertIn('build identity mismatch',result['error'])
                self.assertEqual(masks(wire),[])

    def test_console_restore_failure_does_not_mark_wire_uncertain(self):
        class BrokenRestore:
            def __enter__(self):return Events(key(0x1b))
            def __exit__(self,*_):raise OSError('restore mode')
        root=Path(__file__).resolve().parents[3]
        wire=Wire();identity=Client(Wire()).identify()['build_id'];persisted=[]
        args=SimpleNamespace(action='keyboard',json=False,endpoint_restarted=False,expected_build_id=identity)
        with tempfile.TemporaryDirectory(dir=root/'workdir') as temp, patch('n2m.host.console.Console',return_value=BrokenRestore()), patch('ci.storage.machine_lock',return_value=nullcontext()), patch('n2m.host.command.session',return_value=nullcontext((wire,0,lambda seq,pending:persisted.append(pending),{}))):
            result=command(root,Path(temp),args,{})
        self.assertEqual(result['status'],'FAIL');self.assertIn('restore mode',result['error'])
        self.assertFalse(result['uncertain']);self.assertFalse(persisted[-1]);self.assertEqual(masks(wire),[0])


class NativeConsoleTests(unittest.TestCase):
    def native(self, code=0x10, scan=0x36, down=True):
        kernel=SimpleNamespace(**{name:Mock() for name in ('GetStdHandle','GetConsoleWindow','GetConsoleMode','SetConsoleMode','WaitForSingleObject','ReadConsoleInputW','GetNumberOfConsoleInputEvents')})
        user=SimpleNamespace(GetForegroundWindow=Mock(return_value=7),IsWindowVisible=Mock(return_value=True))
        kernel.GetStdHandle.return_value=3;kernel.GetConsoleWindow.return_value=7
        def mode(handle,out):out._obj.value=0x67;return True
        kernel.GetConsoleMode.side_effect=mode;kernel.SetConsoleMode.return_value=True
        kernel.WaitForSingleObject.return_value=0
        def count(handle,out):out._obj.value=1;return True
        kernel.GetNumberOfConsoleInputEvents.side_effect=count
        def read(handle,out,limit,count):
            out._obj.kind=1;out._obj.data.key.code=code;out._obj.data.key.scan=scan
            out._obj.data.key.down=down;out._obj.data.key.repeat=9;count._obj.value=1
            return True
        kernel.ReadConsoleInputW.side_effect=read
        return kernel,user

    def test_right_shift_edges_focus_and_exact_mode_restore(self):
        kernel,user=self.native()
        with patch('n2m.host.console.os.name','nt'),patch('ctypes.WinDLL',side_effect=[kernel,user],create=True):
            with Console() as console:
                self.assertEqual(console.next_event(),('key',0xa1,True,0))
                user.GetForegroundWindow.return_value=99
                self.assertEqual(console.next_event(),('focus-lost',))
                self.assertEqual(kernel.ReadConsoleInputW.call_count,1)
        self.assertEqual(kernel.SetConsoleMode.call_args_list[-1].args,(3,0x67))

    def test_hidden_console_rejected_without_mode_change(self):
        kernel,user=self.native();user.IsWindowVisible.return_value=False
        with patch('n2m.host.console.os.name','nt'),patch('ctypes.WinDLL',side_effect=[kernel,user],create=True):
            with self.assertRaisesRegex(RuntimeError,'unsupported'):Console().__enter__()
        kernel.SetConsoleMode.assert_not_called()

    def test_read_failure_and_idle(self):
        kernel,user=self.native()
        with patch('n2m.host.console.os.name','nt'),patch('ctypes.WinDLL',side_effect=[kernel,user],create=True):
            with Console() as console:
                kernel.WaitForSingleObject.return_value=258
                self.assertIsNone(console.next_event())
                kernel.WaitForSingleObject.return_value=0;kernel.ReadConsoleInputW.return_value=False
                kernel.ReadConsoleInputW.side_effect=None
                with self.assertRaisesRegex(RuntimeError,'read failed'):console.next_event()


if __name__=='__main__':unittest.main()
