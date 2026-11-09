"""Geometry used only to construct the simulated task and reference captures.

The model-free estimator obtains its geometry from reconstructed RGB-D views,
not from these vertices or an exported simulator mesh.
"""
from .parts import Part
from .palletizing import FOOTPRINT


PLUG = Part(
    "green", "Keyed assembly plug", tuple((x, y, z) for z in (-35., 35.) for x, y in FOOTPRINT),
    (.12, .80, .34, 1.), (46, 75, 38), (95, 255, 255),
    "target_cube", (.42, -.18), (.49, .18), grasp_offset_z=.020,
)
BLOCKER = Part(
    "orange", "Removable obstruction", tuple((x, y, z) for x in (-40., 40.)
                                              for y in (-23., 23.) for z in (-25., 25.)),
    (.95, .43, .06, 1.), (5, 100, 50), (29, 255, 255),
    "target_orange", (.45, -.26), (.30, .15), grasp_offset_z=.008,
)
OBJECTS = {"plug": PLUG, "blocker": BLOCKER}
