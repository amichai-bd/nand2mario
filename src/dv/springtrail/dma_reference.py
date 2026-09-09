"""Literal OAM byte ledger; expectations never come from CPU/DMA output."""
FIRST=bytes(v for i in range(40) for v in (32+i//4*8,16+i%4*8,i,(i%8)*16))
SECOND=bytes([48,32,3,0,48,40,4,32,56,32,5,64,56,40,6,96]+[0]*144)


class DMA:
    def __init__(self, count=2):
        self.count=count
        self.images=(FIRST,SECOND)[:count]
        self.sources=[]; self.reads=[]; self.transfers=[]; self.triggers=[]; self.reports=[]

    def bus(self,dot,address,write,data):
        image=len(self.reports)
        if write and 0xc100<=address<0xc1a0:
            assert image<self.count, 'OAM_EXTRA_SOURCE'
            index=len(self.sources)%160
            assert (address,data)==(0xc100+index,self.images[image][index]), 'OAM_SOURCE'
            self.sources.append(data)
        elif write and address==0xff46:
            assert image<self.count and len(self.sources)==(image+1)*160 and len(self.triggers)==image and data==0xc1, 'OAM_TRIGGER'
            self.triggers.append(dot)
        elif not write and 0xfe00<=address<0xfea0:
            assert image<self.count and len(self.transfers)==(image+1)*160, 'OAM_READ_ORDER'
            index=len(self.reads)%160
            assert (address,data)==(0xfe00+index,self.images[image][index]), f'OAM_READBACK image={image} index={index}'
            assert dot>self.triggers[image]+644, 'OAM_EARLY_RETURN'
            self.reads.append(data)
        elif write and address==0xc0fd:
            assert image<self.count and data==image+1 and len(self.reads)==(image+1)*160, 'OAM_REPORT'
            self.reports.append(dot)

    def transfer(self,dot,index,data):
        image,offset=divmod(len(self.transfers),160)
        assert image<self.count and len(self.triggers)==image+1, 'OAM_TRANSFER_ORDER'
        expected=(self.triggers[image]+8+4*offset,offset,self.images[image][offset])
        assert (dot,index,data)==expected, 'OAM_TRANSFER'
        self.transfers.append(data)

    def finish(self):
        assert len(self.reports)==self.count and all(len(v)==160*self.count for v in (self.sources,self.reads,self.transfers)), 'OAM_MISSING'
        return dict(publications=self.count,bytes_checked=160*self.count,triggers=self.triggers,reports=self.reports)
