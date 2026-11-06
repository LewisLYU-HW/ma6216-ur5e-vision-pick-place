"""Export the shared flat-top stackable block and four coloured metric CADs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import trimesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ma6216.palletizing import PARTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    files=[]
    for part in PARTS:
        path=args.output/f'{part.key}_model_m.obj';part.export_mesh(path);files.append(path)
    mesh=PARTS[0].mesh()
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:
        raise ValueError('Stackable block is not a closed printable solid')
    printable=mesh.copy();printable.apply_scale(1000.);printable.apply_translation([0,0,20.])
    stl=args.output/'stack_block_print_mm.stl';printable.export(str(stl));files.append(stl)
    restored=trimesh.load(stl,force='mesh')
    if not restored.is_watertight or not np.allclose(restored.extents,[80.,50.,40.],atol=1e-4):
        raise ValueError('STL round-trip validation failed')
    manifest={'model':'flat-top block with one cropped vertical corner','size_mm':[80,50,40],
              'copies_for_demo':4,'simulation_mass_kg_per_block':.1,'model_units':'metres','print_units':'millimetres',
              'print_translation_mm':[0,0,20],'watertight':True,'volume_mm3':float(mesh.volume*1e9),
              'files':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
