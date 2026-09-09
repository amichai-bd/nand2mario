"""Validate the original Springtrail display encoding before assembly."""
import re
from .expressions import AssemblyError


def decode(data, tiles=94):
    def bad():
        raise AssemblyError('COLUMN_ENCODING','exact bounded sixteen-row column required')
    if not isinstance(data,list) or not 1<=len(data)<=33: bad()
    if any(type(n) is not int or not 0<=n<=255 for n in data): bad()
    out=[]; index=0
    while index<len(data):
        count=data[index]; index+=1
        if count==0:
            if index!=len(data) or len(out)!=16: bad()
            return out
        if count>16 or index==len(data) or len(out)+count>16: bad()
        tile=data[index]; index+=1
        if tile>=tiles: bad()
        out.extend([tile]*count)
    bad()


def validate(root):
    tree=root/'src/sw/springtrail'
    lines=[line.split(';')[0].strip() for line in (tree/'columns.asm').read_text().splitlines()]
    lines=[line for line in lines if line]
    prefix=['SECTION "columns",ROM','ColumnPointers:']+['DW DisplayColumn'+str(i) for i in range(96)]
    if lines[:98]!=prefix or len(lines)!=290:
        raise AssemblyError('COLUMN_ENCODING','exact indexed96-column table required')
    columns=[]
    for i in range(96):
        label,values=lines[98+i*2:100+i*2]
        if label!='DisplayColumn'+str(i)+':' or not re.fullmatch(r'DB [0-9]+(?:,[0-9]+)*',values):
            raise AssemblyError('COLUMN_ENCODING','invalid column label or bytes')
        columns.append(decode([int(n) for n in values[3:].split(',')]))
    world=[[int(n) for n in line[3:].split(',')] for line in (tree/'world.asm').read_text().splitlines() if line.startswith('DB ')]
    if len(world)!=18 or any(len(row)!=96 for row in world):
        raise AssemblyError('COLUMN_WORLD','literal96x18 collision world required')
    if any(columns[x][y]!=world[y+2][x] for x in range(96) for y in range(16)):
        raise AssemblyError('COLUMN_WORLD','display columns differ from unchanged terrain')
    return columns
