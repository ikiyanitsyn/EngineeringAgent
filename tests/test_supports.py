import numpy as np

from engagent.fea.deck import free_rigid_motions


def _bar():
    return np.array([[x, y, z] for x in (0, 500) for y in (0, 20) for z in (0, 20)], float)


def test_spin_about_the_axis_is_found():
    n = _bar()
    h = np.zeros((8, 3), bool)
    h[n[:, 0] == 0, 0] = True                     # end face slides in x
    h[(n == 0).all(axis=1)] = True                # one corner pinned
    assert free_rigid_motions(n, h) == ["rotate about X"]
    h[(n[:, 0] == 0) & (n[:, 1] == 20) & (n[:, 2] == 0), 2] = True   # a third point stops the spin
    assert free_rigid_motions(n, h) == []


def test_a_fixed_face_holds_everything_and_nothing_held_moves():
    n = _bar()
    h = np.zeros((8, 3), bool)
    h[n[:, 0] == 0] = True
    assert free_rigid_motions(n, h) == []
    assert free_rigid_motions(n, np.zeros((8, 3), bool))
