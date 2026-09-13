"""Current fixed-route host protocol and aligned pixels; no board evidence."""
import tempfile
import unittest
from pathlib import Path

import state_support as support
from state_fake import Endpoint
from n2m.host.client import Client
from n2m import springtrail_acquisition as acquisition


class AcquisitionHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image,cls.binding = support.binding()

    def run_plan(self,plan,*,defect=None,budget=None,pixel_fault=False):
        endpoint = Endpoint(image=self.image,defect=defect)
        client = Client(endpoint)
        if pixel_fault:
            snapshot = client.snapshot
            def corrupt():
                meta,data = snapshot()
                return meta,bytes((data[0]^1,))+data[1:]
            client.snapshot = corrupt
        with tempfile.TemporaryDirectory() as folder:
            result = acquisition.run(client,self.image,self.binding,Path(folder),
                                     plan=plan,budget=budget,write_png=lambda pixels,path:None)
        return result,endpoint

    def test_complete_short_and_full_keep_exact_route_and_cleanup(self):
        for plan,frames,names in (('thrower-short',244,['title','large']),
                                 ('thrower',411,['title','large','promoted','shot'])):
            with self.subTest(plan=plan):
                result,endpoint = self.run_plan(plan)
                self.assertEqual(result['status'],'PASS',result.get('reason'))
                self.assertEqual(result['frames'],frames)
                self.assertEqual([r['name'] for r in result['captures']],names)
                self.assertTrue(all(r['checked_pixels']==23040 for r in result['captures']))
                self.assertTrue(result['cleanup']['verified'])
                self.assertEqual(endpoint.mask,0)
                if plan == 'thrower':
                    self.assertEqual((endpoint.game.world.power,endpoint.game.world.shot.ttl),(2,62))

    def test_stopped_route_cannot_satisfy_completion(self):
        for options,reason in (({'budget':{'frames':3}},'STATE_BUDGET_FRAMES'),
                               ({'defect':'ignore-input'},'ACQUISITION_STATE'),
                               ({'defect':'short-run'},'STATE_RUN_STOPPED'),
                               ({'pixel_fault':True},'ACQUISITION_PIXELS')):
            with self.subTest(options=options):
                result,_ = self.run_plan('thrower-short',**options)
                self.assertEqual(result['status'],'FAIL')
                self.assertIn(reason,result['reason'])
                self.assertTrue(result['cleanup']['verified'])
