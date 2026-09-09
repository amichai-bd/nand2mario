import unittest
from dma_reference import DMA, FIRST, SECOND


def feed(check, fault=None):
    for image,data in enumerate(check.images):
        base=1000+image*10000
        for i,value in enumerate(data):check.bus(base+i,0xc100+i,1,value)
        check.bus(base+200,0xff46,1,0xc1)
        for i,value in enumerate(data):check.transfer(base+208+4*i,i,value)
        for i,value in enumerate(data):
            if fault=='missing' and image==1 and i==159:continue
            if fault=='wrong' and image==0 and i==159:value=0
            if fault=='stale' and image==1 and i==159:value=FIRST[i]
            check.bus(base+1100+i,0xfe00+i,0,value)
        check.bus(base+1500,0xc0fd,1,image+1)
    return check.finish()


class PublisherTests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(feed(DMA())['bytes_checked'],320)
        self.assertEqual(feed(DMA(1))['bytes_checked'],160)
        self.assertEqual(FIRST[-4:],bytes([104,40,39,112]))
        self.assertEqual(SECOND[16:],bytes(144))

    def test_wrong_last_byte(self):
        with self.assertRaisesRegex(AssertionError,'OAM_READBACK'):feed(DMA(),'wrong')

    def test_stale_tail(self):
        with self.assertRaisesRegex(AssertionError,'OAM_READBACK'):feed(DMA(),'stale')

    def test_missing_last(self):
        with self.assertRaisesRegex(AssertionError,'OAM_REPORT'):feed(DMA(),'missing')

    def test_incomplete(self):
        with self.assertRaisesRegex(AssertionError,'OAM_MISSING'):DMA().finish()
