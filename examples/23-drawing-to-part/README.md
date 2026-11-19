# Drawing to part

`mounting_plate_A3.pdf` is a simple A3 drawing: a 120 x 60 x 8 mm aluminium 6061-T6 plate with four
Ø6.6 through holes on a 100 x 40 mm pattern (10 mm from each edge), general tolerance ISO 2768-m.

Try it in a request issue (needs the hosted AI model, e.g. the free Gemini key):

> Model the part in `examples/23-drawing-to-part/mounting_plate_A3.pdf`. Check it as a cantilever:
> fix the left 60 mm end face, 300 N down on the right end face.

Expected: a 120 x 60 x 8 mm plate with 4 holes; the material comes from the title block. Hand check
for the root bending stress without holes: 6 P L / (b t^2) = 6 x 300 x 120 / (60 x 8^2) = 56.3 MPa
(the holes near the root raise the local peak).
