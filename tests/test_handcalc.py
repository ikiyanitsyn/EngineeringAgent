import math

import pytest

from engagent import handcalc as H


def val(name, inputs, key, system="metric"):
    return H.run(name, inputs, system).value(key)


def test_cantilever_guide_values():
    i = {"P": 100, "L": 100, "E": "210 GPa", "b": 10, "h": 10}
    assert val("beam.cantilever_end_load", i, "deflection") == pytest.approx(0.19048, rel=1e-4)
    assert val("beam.cantilever_end_load", i, "stress") == pytest.approx(60.0)
    assert val("beam.cantilever_end_load", {**i, "x": 20}, "stress_at_x") == pytest.approx(48.0)
    with_shear = val("beam.cantilever_end_load", {**i, "nu": 0.3}, "deflection")
    assert 0.19048 < with_shear < 0.19048 * 1.02


def test_same_answer_in_imperial():
    m = val("beam.cantilever_end_load", {"P": 100, "L": 100, "E": 210000, "b": 10, "h": 10}, "deflection")
    i = val("beam.cantilever_end_load", {"P": "22.4809 lbf", "L": 3.93701, "E": "30.4579 Msi", "b": 0.393701,
                                         "h": 0.393701}, "deflection", "imperial")
    assert i == pytest.approx(m, rel=1e-4)


def test_beams():
    b = {"L": 1000, "E": 200000, "I": 1e6, "c": 50}
    assert val("beam.simply_supported_center_load", {"P": 1000, **b}, "deflection") == pytest.approx(1000 * 1e9 / (48 * 2e11))
    assert val("beam.simply_supported_udl", {"w": 2, **b}, "moment") == pytest.approx(2 * 1e6 / 8)
    assert val("beam.fixed_fixed_udl", {"w": 2, **b}, "deflection") == pytest.approx(2 * 1e12 / (384 * 2e11))


def test_buckling_and_frequency():
    r = H.run("column.euler_buckling", {"L": 200, "E": 210000, "b": 10, "h": 10, "ends": "fixed_free"}, "metric")
    assert r.value("P_cr") == pytest.approx(math.pi**2 * 210000 * 833.333 / 400**2, rel=1e-4)
    f = val("beam.natural_frequency", {"L": 100, "E": 210000, "b": 10, "h": 10, "density": 7850}, "f1")
    assert f == pytest.approx(835.5, rel=2e-3)


def test_plate_kt_pressure():
    assert val("plate.rectangular_uniform", {"q": 0.1, "a": 100, "b": 100, "t": 2, "E": 200000}, "stress") == \
        pytest.approx(0.2874 * 0.1 * 100**2 / 4)
    assert val("kt.plate_hole_tension", {"P": 10000, "w": 50, "d": 10, "t": 5}, "Kt") == pytest.approx(2.506, abs=2e-3)
    assert val("pressure.thin_cylinder", {"p": 1, "D": 101, "t": 1}, "hoop_stress") == pytest.approx(50.0)
    assert val("pressure.thick_cylinder", {"p": 10, "ri": 10, "ro": 20}, "hoop_stress_inner") == pytest.approx(16.667, rel=1e-3)


def test_thermal():
    c = {"k": 50, "A": 100, "L": 100, "T_hot": 100, "T_cold": 20}
    assert H.run("thermal.conduction_slab", c, "metric").text("heat_flow") == "4 W"
    assert val("thermal.restrained_bar", {"E": "210 GPa", "cte": "12 um/m/K", "dT": 50}, "stress") == pytest.approx(-126.0)
    r = H.run("thermal.slab_transient", {"k": 0.55, "density": 1600, "cp": 1100, "thickness": 4, "T_initial": 20,
                                         "T_ambient": 385, "time": 1e6}, "metric")
    assert r.value("T_center") == pytest.approx(385.0)
    t = val("thermal.lumped_transient", {"density": 2700, "cp": 900, "V": 1000, "h": 100, "A": 600}, "tau")
    # V is read in cm^3 (metric default for volume): 2700 * 900 * 1e-3 m^3 / (100 * 600e-6 m^2)
    assert t == pytest.approx(40500.0)


def test_fatigue_and_bolts():
    se = val("fatigue.endurance_limit", {"uts": 630, "size": 20}, "Se")
    assert se == pytest.approx(0.5 * 630 * 4.51 * 630**-0.265 * 1.24 * 20**-0.107, rel=1e-4)
    n = val("fatigue.mean_stress", {"stress_alt": 100, "stress_mean": 100, "Se": 200, "uts": 600}, "n_goodman")
    assert n == pytest.approx(1 / (0.5 + 1 / 6))
    assert val("bolt.preload_torque", {"size": "M8", "grade": "8.8"}, "preload") == pytest.approx(0.75 * 600 * 36.6)


def test_composites():
    r = H.run("composite.laminate", {"material": "cf_peek_ud", "layup": "[0/45/-45/90]s"}, "metric")
    assert r.value("Ex") == pytest.approx(r.value("Ey"), rel=1e-6)                 # quasi-isotropic
    assert r.value("Gxy") == pytest.approx(r.value("Ex") / (2 * (1 + r.value("nuxy"))), rel=1e-6)
    ud = H.run("composite.laminate", {"material": "cf_peek_ud", "layup": [0, 0, 0, 0]}, "metric")
    assert ud.value("Ex") == pytest.approx(138000, rel=1e-6)
    assert ud.value("alpha_z") == pytest.approx(28e-6, rel=1e-6)
    s = val("composite.spring_in", {"angle": 90, "alpha_inplane": "2.7 um/m/K", "alpha_thickness": "38.6 um/m/K",
                                    "dT": -290}, "delta_angle")
    assert s == pytest.approx(90 * (2.7 - 38.6) * 1e-6 * -290 / (1 + 38.6e-6 * -290), rel=1e-6)


def test_errors_are_helpful():
    with pytest.raises(KeyError, match="did you mean"):
        H.run("beam.cantilever_end_lod", {}, "metric")
    with pytest.raises(ValueError, match="missing input"):
        H.run("axial.bar", {"P": 1}, "metric")
    with pytest.raises(ValueError, match="unknown input"):
        H.run("axial.bar", {"P": 1, "L": 1, "A": 1, "E": 1, "bogus": 2}, "metric")
    assert len(H.catalog()) >= 40
