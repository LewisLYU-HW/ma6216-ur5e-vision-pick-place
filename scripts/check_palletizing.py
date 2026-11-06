"""Check stack CAD and reject floating objects that merely look aligned."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ma6216.palletizing import PARTS,BY_KEY,build_pallet_scene,set_pose,block_outcome
from ma6216.scene import mujoco


def main():
    mesh=PARTS[0].mesh()
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0
    assert np.allclose(mesh.extents,[.080,.050,.040])
    # Independent test fixture, never used by the manipulation controller.
    model,data=build_pallet_scene()
    base=np.eye(4);base[:3,3]=[.40,.18,.409]
    upper=base.copy();upper[2,3]=.450  # Aligned, but floating 1 mm above the base.
    set_pose(data.qpos,model,BY_KEY['green'],base)
    set_pose(data.qpos,model,BY_KEY['purple'],upper)
    mujoco.mj_forward(model,data)
    floating=block_outcome(model,data,BY_KEY['purple'])
    assert not floating['success'] and floating['support_normal_force_n']==0.
    for _ in range(2500):mujoco.mj_step(model,data)
    settled=block_outcome(model,data,BY_KEY['purple'])
    assert settled['success'] and settled['support']=='green' and settled['support_normal_force_n']>.2
    print(json.dumps({'cad_watertight':True,'dimensions_m':mesh.extents.tolist(),
                      'floating_aligned_block_rejected':True,'physical_upper_on_lower_accepted':True,
                      'upper_support_normal_force_n':settled['support_normal_force_n']}))


if __name__=='__main__':main()
