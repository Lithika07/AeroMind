# AeroMind simulation assets

Everything AeroMind flies in lives here, so the project needs no other checkout.

| Path | What | Origin |
|---|---|---|
| `worlds/aero_sense_disaster.sdf` | The Aero Sense disaster world (earthquake + flood sectors), unchanged | Aero Sense (`~/sih_2026`), copied 2026-10-22 |
| `models/aero_sense_*` | Its buildings, roads, ground, poles, power lines, zone signs | Aero Sense |
| `models/bus, hatchback, pickup, radio_tower, water_tower, collapsed_*` | Vehicles and landmark structures | [tdf_gazebo](https://github.com/rsanchezmo/tdf_gazebo), MIT (`third_party/LICENSE.tdf_gazebo`) |
| `models/jersey_barrier`, `models/aero_sense_roads/materials/textures/Asphalt01_*` | Barriers, asphalt textures | [darpa_subt_worlds](https://github.com/LTU-RAI/darpa_subt_worlds), MIT (`third_party/LICENSE.darpa_subt_worlds`) |
| `models/aero_sense_ground/.../grass_green.png`, `models/bus/.../wheels_01.png` | Procedural replacements (upstream files are GPL-3 / unlicensed) | `tools/make_textures.py` |
| `models/aeromind_hexa` | The Hexa-X airframe, payload sensors removed | Aero Sense airframe; prop meshes from ardupilot_gazebo, LGPL-3 (`third_party/LICENSE.ardupilot_gazebo`) |
| `params/copter.parm` | ArduCopter SITL defaults | ArduPilot `Tools/autotest/default_params`, GPL-3 |
| `params/hexa.parm` | Hexa-X frame, EKF3 | Aero Sense |

The casualty models (`aero_sense_people`) are not copied: the world file does not include them
(the Aero Sense launch spawns them), and AeroMind does not need them.

External software still required (installed, not copied): Gazebo Harmonic (`gz sim` 8), the
`ardupilot_gazebo` system plugin (`GZ_SIM_SYSTEM_PLUGIN_PATH`), an `arducopter` SITL binary,
MAVProxy and pymavlink.
