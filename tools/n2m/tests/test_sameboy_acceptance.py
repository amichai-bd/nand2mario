import json
from pathlib import Path
import tempfile
import unittest
from src.dv.sameboy.compare_acceptance import require_producers


class ProducerIdentity(unittest.TestCase):
    def test_failed_producer_rejected_before_trace_comparison(self):
        for failed in ('core','dut'):
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as temporary:
                base=Path(temporary)
                for name in ('core','dut'):
                    (base/name).mkdir()
                    (base/name/'result.json').write_text(json.dumps({'status':'FAIL' if name==failed else 'PASS'}))
                with self.assertRaisesRegex(ValueError,'producer status: expected=PASS'):
                    require_producers(base/'core/observations.log',base/'dut')

    def test_wrong_image_rejected_even_with_successful_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            for name in ('core','dut'):(base/name).mkdir()
            (base/'core/result.json').write_text(json.dumps({
                'status':'PASS','pin':'213a12ce93d66b105a113debd9396306066a7cfc',
                'observation_mode':'observed-cycle-path','commands':[{'returncode':0}],
                'inputs':{'image':'0'*64}}))
            (base/'dut/result.json').write_text(json.dumps({'status':'PASS'}))
            with self.assertRaisesRegex(ValueError,'Core image identity differs'):
                require_producers(base/'core/observations.log',base/'dut')
