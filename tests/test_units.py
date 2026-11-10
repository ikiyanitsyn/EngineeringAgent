import pytest

from engagent import units as U


def test_length_and_force():
    assert U.to_internal("1 in", "length") == pytest.approx(25.4)
    assert U.to_internal("1 lbf", "force") == pytest.approx(4.4482216)
    assert U.to_internal(10, "length", "imperial") == pytest.approx(254.0)
    assert U.to_internal(10, "length", "metric") == 10


def test_pressure_and_modulus():
    assert U.to_internal("210 GPa", "pressure") == pytest.approx(210000)
    assert U.to_internal("30e6 psi", "pressure") == pytest.approx(206842.7, rel=1e-5)
    assert U.from_internal(1.0, "pressure", "imperial") == pytest.approx(145.0377, rel=1e-5)


def test_density_solver_units():
    assert U.to_internal(7850, "density", "metric") == pytest.approx(7.85e-9)
    assert U.to_internal("0.2836 lbm/in3", "density") == pytest.approx(7.85e-9, rel=1e-3)


def test_temperature_offsets():
    assert U.to_internal("212 degF", "temperature") == pytest.approx(100.0)
    assert U.to_internal("373.15 K", "temperature") == pytest.approx(100.0)
    assert U.to_internal("90 degF", "temp_delta") == pytest.approx(50.0)
    assert U.from_internal(100.0, "temperature", "imperial") == pytest.approx(212.0)


def test_thermal_properties_guide_table():
    # values from the original guide's conversion table (mm, tonne, s, K, mW)
    assert U.to_internal(1, "conductivity", "metric") == pytest.approx(1.0)        # W/m/K -> mW/mm/K
    assert U.to_internal(1, "specific_heat", "metric") == pytest.approx(1e6)       # J/kg/K -> mJ/tonne/K
    assert U.to_internal(1, "film", "metric") == pytest.approx(1e-3)               # W/m2/K -> mW/mm2/K
    assert U.to_internal(1, "heat_flux", "metric") == pytest.approx(1e-3)
    assert U.to_internal(1, "power", "metric") == pytest.approx(1e3)               # W -> mW
    assert U.to_internal("1 BTU/hr/ft/F", "conductivity") == pytest.approx(1.7307, rel=1e-3)
    assert U.to_internal("1 BTU/lbm/F", "specific_heat") == pytest.approx(4186.8e6, rel=1e-3)
    assert U.to_internal("1 BTU/hr/ft2/F", "film") == pytest.approx(5.678e-3, rel=1e-3)


def test_round_trip_all_kinds():
    for kind in U.KINDS:
        for system in U.SYSTEMS:
            v = U.to_internal(3.7, kind, system)
            assert U.from_internal(v, kind, system) == pytest.approx(3.7)


def test_formatting_and_errors():
    assert U.fmt(25.4, "length", "imperial") == "1 in"
    assert U.fmt(0.19048, "length", "metric") == "0.1905 mm"
    assert U.fmt_vec([100, 1e-15, -5], "length", "metric") == "(100, 0, -5) mm"
    with pytest.raises(ValueError):
        U.to_internal("5 furlongs", "length")
    with pytest.raises(ValueError):
        U.normalize_system("cgs")


def test_toggle_follows_environment(imperial):
    from engagent import config
    assert config.get_units() == "imperial"
    assert config.get_standard() == "asme"
    assert U.default_unit("pressure") == "psi"
    assert U.to_internal(1, "length") == pytest.approx(25.4)
