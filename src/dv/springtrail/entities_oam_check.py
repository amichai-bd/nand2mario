"""Current scene state, ordered complete shadow writes and capacity canaries."""
import entities_oam_cases as cases
from motion_unit_check import Check as StateCheck, run as run_state


class Check(StateCheck):
    def __init__(self, short=False, part=None):
        super().__init__(short, cases, part)
        self.shadow_writes=[]

    def write(self,dot,address,data):
        if address==0xc0fc:
            self.shadow_writes=[]
        elif self.active is not None and address!=0xc0fd:
            row=self.selected[len(self.reports)]
            if row['kind']=='limit':
                assert 0xdfe0<=address<0xdffe, 'ENTITY_OAM_LIMIT_WRITE'
            elif 0xc100<=address<0xc1a0:
                self.shadow_writes.append((address,data))
            else:
                assert 0xc034<=address<0xc04c or 0xdfe0<=address<0xdffe, 'ENTITY_OAM_UNRELATED_WRITE'
        if address==0xc0fd:
            assert self.active is not None and data==len(self.reports)+1, 'ENTITY_OAM_REPORT'
            assert self.shadow_writes==self.selected[data-1]['writes'], 'ENTITY_OAM_ORDER'
        super().write(dot,address,data)


async def run(dut,short=False,part=None):
    await run_state(dut,short=short,suite=cases,part=part,checker=Check(short,part))
