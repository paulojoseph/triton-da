A slicer for layered (additive) manufacturing needs exact per-layer measurements of a part. Under `/app/data/` you'll find `mesh.obj` — a closed, watertight, outward-oriented triangle mesh of a metal part whose vertex coordinates are integers — and `heights.json`, a JSON array of integer slice heights. The part is built up the +z axis, one horizontal layer at a time, in increasing height order; the layer for a height `h` is the cross-section of the solid bounded by the mesh with the plane `z = h`.

The part is not convex and need not be simply connected: a single layer can contain several disjoint solid pieces, and a piece can enclose holes. A slice plane may also pass exactly through vertices or edges of the mesh; these cases are part of the data and must be handled exactly, not by nudging the plane off them. We run the same tool on other parts, so it must work from the files rather than from hard-coded answers.

Write your program to `/app/slice.py` so that running `python3 /app/slice.py` reads those two files and writes `/app/result.json`. For every height, in the same order as `heights.json`, measure the cross-section at `z = h` and report:

- `regions` — the integer number of disjoint solid pieces making up the cross-section.
- `holes` — the integer total number of holes across those pieces (a solid disk has 0, an annulus has 1).
- `area` — the filled cross-section area (the area of the holes is excluded), in squared coordinate units.
- `perimeter` — the combined length of every boundary loop of the cross-section (outer boundaries and holes).
- `centroid` — the area centroid `[cx, cy]` of the filled region (holes excluded), in the mesh's x,y coordinates.
- `overhang_area` — the area of this layer's cross-section that does **not** lie directly above the previous layer's cross-section, i.e. the area of `region(h) \ region(h_prev)`, where `h_prev` is the height listed immediately before `h`. For the first height in the list this is `0` (the layer rests on the build plate).
- `layer_volume` — the volume of solid lying in the slab between the previous slice height and this one (`h_prev < z <= h`), i.e. the material deposited for this layer. For the first height in the list, report the volume of solid below that height (`z <= h`).

Write `/app/result.json` as a JSON array with one object per height, in order, each having the keys `regions`, `holes`, `area`, `perimeter`, `centroid`, `overhang_area`, and `layer_volume`. `regions` and `holes` are integers; `centroid` is a two-element list of numbers; the rest are numbers in the mesh's coordinate units (areas in units squared, volumes in units cubed).
