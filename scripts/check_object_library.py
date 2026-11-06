"""Check source hashes and verify that the hex nut's hole is physically open."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ma6216.config import project_root
from ma6216.object_library import DIVERSE_PARTS
from ma6216.scene import mujoco


def main():
    source=project_root()/"assets/library/gso"
    manifest=json.loads((source/"SOURCE.json").read_text())
    for row in manifest["files"]:
        if hashlib.sha256((source/row["path"]).read_bytes()).hexdigest()!=row["sha256"]:
            raise ValueError(f"Source checksum mismatch: {row['path']}")
    nut=next(p for p in DIVERSE_PARTS if p.key=="hex_nut")
    if not nut.mesh().is_watertight:
        raise ValueError("Nut CAD is not watertight")
    spec=mujoco.MjSpec()
    nut.configure(spec)
    probe_body=spec.worldbody.add_body(name="probe_carrier",mocap=True)
    probe_body.add_geom(name="probe",type=mujoco.mjtGeom.mjGEOM_SPHERE,size=[.005,0,0])
    model=spec.compile()
    data=mujoco.MjData(model)
    mujoco.mj_forward(model,data)
    probe=model.geom("probe").id
    def probe_contacts():
        return [float(c.dist) for c in data.contact if probe in (int(c.geom1),int(c.geom2)) and c.dist<0]
    if probe_contacts():
        raise ValueError("A 10 mm sphere does not fit through the 26 mm hole")
    data.mocap_pos[0]=[.022,0,0]
    mujoco.mj_forward(model,data)
    if not probe_contacts():
        raise ValueError("Probe did not collide with the solid wall of the nut")
    if not np.isclose(model.body_mass[model.body(nut.body).id],nut.mass_kg):
        raise ValueError("Compound object mass is inconsistent")
    print(json.dumps({"source_files_verified":len(manifest["files"]),
                      "nut_watertight":True,"hole_probe_no_collision":True,"wall_probe_collision":True,
                      "nut_collision_pieces":len(nut.collision_names)}))


if __name__=="__main__":
    main()
