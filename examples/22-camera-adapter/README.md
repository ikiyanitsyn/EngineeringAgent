# Camera adapter: your own two parts (stage 1)

`arm_flange.step` is a robot tool flange to ISO 9409-1-50-4-M6: a 63 mm disc with 4 x M6 tapped holes
on a 50 mm bolt circle. `camera.step` is a camera body with 4 x M6 tapped holes in a 30 x 40 mm
rectangle underneath.

    ./ea cad features examples/22-camera-adapter/camera.step --png camera.png

In a GitHub issue, attach a **.zip** with your STEP files (GitHub does not accept .step attachments), or
upload them into the repository and write their paths. The bot replies with:
- numbered faces and hole patterns per part (`features.json`);
- labelled pictures (`faces_*.png`, two views so every side is shown);
- a question asking which faces to join.

A 5.0 mm hole is listed as "M5 at nominal size or M6 tapped". The tool shows both and asks you to
confirm; it does not guess.

## Stage 2: the adapter

Reply `join arm_flange F2 to camera F2, M6`. The bot designs a flat adapter plate:
- clearance holes and counterbores for both screw patterns;
- part B turned, and only if needed shifted, so every hole clears its neighbours and one set of screws
  can still be reached during assembly;
- the assembly order, the screws (ISO 4762, sized to the measured depth of the threaded holes), the
  plate STEP / STL / 3MF and an assembly STEP with a picture.

For these two parts a centred plate cannot be assembled. The camera's M6 screws would sit on the flange
ring and the flange's screws under the camera, so the bot shifts the camera 32 mm and says so. If no flat
plate works it explains why and asks which alternative you want; it never returns a part that cannot be
assembled.

Next (stage 3): give the top part's weight and the acceleration and the plate is checked with FEA and a
hand calculation.
