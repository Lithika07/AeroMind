"""Limits of the flying site (the disaster world), which every mission edit must respect.

Positions are world ENU metres from the site origin, the same frame as sim/scenarios.yaml.
"""
SITE_ORIGIN = (-35.363262, 149.165237)
#: 16.4 m buildings and 9 m overhead wires, plus clearance. The PRD's 10 m floor would hit them.
MIN_ALT_M = 25.0
#: 400 ft green-zone ceiling under India's drone rules.
MAX_ALT_M = 120.0
#: name -> (east, north, height_m, horizontal clearance_m)
OBSTACLES = {"radio_mast": (-40.0, 60.0, 44.0, 20.0)}
VERTICAL_MARGIN_M = 6.0
