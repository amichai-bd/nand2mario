"""Original strict shade-array conversion; no palette inference or deduplication."""
import json
from .expressions import AssemblyError


def fail(code, cause, file='asset.json', line=1, column=1):
    error=AssemblyError(code,cause,{'file':file,'line':line,'column':column})
    error.diagnostic['stage']='assets'
    raise error


def validate_shades(value, file='asset.json'):
    if type(value) is not dict or set(value)!={'schema_version','width','height','pixels'}:
        fail('ASSET_SCHEMA','shade object requires exactly schema_version,width,height,pixels',file)
    if type(value['schema_version']) is not int or value['schema_version']!=1:
        fail('ASSET_SCHEMA','unsupported shade schema version',file)
    width,height=value['width'],value['height']
    if any(type(n) is not int or n<=0 or n%8 for n in [width,height]):
        fail('ASSET_DIMENSIONS','dimensions must be positive exact integers divisible by 8',file)
    pixels=value['pixels']
    if type(pixels) is not list or len(pixels)!=height:
        fail('ASSET_PIXELS','pixel row count must equal height',file)
    for y,row in enumerate(pixels):
        if type(row) is not list or len(row)!=width:
            fail('ASSET_PIXELS',f'row {y} must contain exactly width pixels',file)
        for x,shade in enumerate(row):
            if type(shade) is not int or not 0<=shade<=3:
                fail('ASSET_PIXELS',f'pixel x={x} y={y} must be an exact integer shade 0..3',file)
    return value


def load_shades(path, file):
    def fields(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('duplicate JSON key: '+key)
            obj[key]=value
        return obj
    try:
        data=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=fields)
    except json.JSONDecodeError as error:
        fail('ASSET_JSON',error.msg,file,error.lineno,error.colno)
    except (ValueError,UnicodeError,OSError) as error:
        # Keep diagnostics target-relative; OS messages may contain private paths.
        fail('ASSET_JSON','invalid/unreadable UTF-8 shade JSON: '+type(error).__name__,file)
    return validate_shades(data,file)


def encode_shades(value, file='asset.json'):
    data=validate_shades(value,file)
    result=bytearray()
    for tile_y in range(0,data['height'],8):
        for tile_x in range(0,data['width'],8):
            for row in range(8):
                low=high=0
                for column in range(8):
                    shade=data['pixels'][tile_y+row][tile_x+column]
                    low=(low<<1)|(shade&1)
                    high=(high<<1)|((shade>>1)&1)
                result.extend([low,high])
    assert len(result)==data['width']*data['height']//4
    return bytes(result)
