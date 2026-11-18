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
