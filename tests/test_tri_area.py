import numpy as np

from engagent.fea.mesh import tri_area_vectors


def test_quadratic_triangle_area_uses_midside_nodes():
    # a quarter-circle-ish curved triangle: mid-side node 1-2 bulges outward in-plane
    nodes = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0, 0], [0.6, 0.6, 0], [0, 0.5, 0]], float)
    lin = np.linalg.norm(tri_area_vectors(nodes, np.array([[1, 2, 3]])))
    quad = np.linalg.norm(tri_area_vectors(nodes, np.array([[1, 2, 3, 4, 5, 6]])))
    assert abs(lin - 0.5) < 1e-12
    assert quad > lin                       # the bulge adds area


def test_flat_quadratic_triangle_matches_linear():
    nodes = np.array([[0, 0, 0], [2, 0, 0], [0, 1, 0], [1, 0, 0], [1, 0.5, 0], [0, 0.5, 0]], float)
    a = tri_area_vectors(nodes, np.array([[1, 2, 3, 4, 5, 6]]))
    assert np.allclose(a, [[0, 0, 1.0]])
