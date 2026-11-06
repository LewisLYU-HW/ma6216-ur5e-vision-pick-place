"""Export diverse CADs and verified, millimetre-scale printable mesh copies."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import trimesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ma6216.object_library import DIVERSE_PARTS,SCREWDRIVER


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    records=[]
    for part in (*DIVERSE_PARTS,SCREWDRIVER):
        mesh=part.mesh()
        obj=args.output/f"{part.key}_model_m.obj"
        mesh.export(str(obj))
        printable=mesh.copy()
        before=len(printable.vertices)
        # Remove duplicate seam vertices, preserving all triangle positions.
        # This changes topology at texture seams, never the source asset files.
        printable.merge_vertices(merge_tex=True,merge_norm=True)
        ready=bool(printable.is_watertight and printable.is_winding_consistent and printable.volume>0)
        row={"id":part.key,"size_mm":(mesh.extents*1000).tolist(),"printable_closed_solid":ready,
             "merged_duplicate_vertices":before-len(printable.vertices),
             "model_units":"metres","print_units":"millimetres",
             "print_translation_mm":[0,0,part.half_height*1000],"simulation_mass_kg":part.mass_kg,
             "source":"Google Scanned Objects, CC-BY-4.0" if part.key in ("hammer","screwdriver") else "Project parametric geometry",
             "source_uniform_scale":.5 if part.key in ("hammer","screwdriver") else 1.,
             "files":{obj.name:hashlib.sha256(obj.read_bytes()).hexdigest()}}
        if ready:
            printable.apply_scale(1000.)
            printable.apply_translation(row["print_translation_mm"])
            stl=args.output/f"{part.key}_print_mm.stl"
            printable.export(str(stl))
            restored=trimesh.load(stl,force="mesh")
            if not restored.is_watertight or not np.allclose(restored.extents,mesh.extents*1000,atol=1e-3):
                raise RuntimeError(f"Printable mesh round-trip failed for {part.key}")
            row["files"][stl.name]=hashlib.sha256(stl.read_bytes()).hexdigest()
        records.append(row)
    (args.output/"manifest.json").write_text(json.dumps(records,indent=2)+"\n")
    print(json.dumps(records,indent=2))


if __name__=="__main__":
    main()
