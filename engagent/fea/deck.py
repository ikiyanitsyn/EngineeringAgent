"""Write a CalculiX input deck (.inp) from a Job and a Mesh.

Internal unit system throughout: mm, tonne, s, N, MPa, mJ, mW, degC.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import units as U
from .job import Job
from .mesh import AXES, FaceSet, Mesh

SIGMA_SB = 5.670374419e-11      # mW / (mm^2 K^4)
ABS_ZERO = -273.15
G0 = 9806.65                    # mm/s^2


def _ids(f, ids, per=12):
    ids = list(int(i) for i in ids)
    for i in range(0, len(ids), per):
        f.write(", ".join(str(v) for v in ids[i:i + per]) + "\n")


def _surface_elsets(f, name: str, fs: FaceSet) -> list[int]:
    """Write one ELSET per CalculiX face number; return the face numbers present."""
    present = []
    for fn in (1, 2, 3, 4):
        el = fs.elem_faces[fs.elem_faces[:, 1] == fn][:, 0]
        if len(el):
            f.write(f"*ELSET, ELSET=E_{name}_S{fn}\n")
            _ids(f, el)
            present.append(fn)
    return present


def permute_ortho(p: dict, order: tuple[int, int, int]) -> dict:
    """Engineering constants re-expressed with local axis i taken from material axis order[i]."""
    E = {1: p["E1"], 2: p["E2"], 3: p["E3"]}
    nu = {(1, 2): p["nu12"], (1, 3): p["nu13"], (2, 3): p["nu23"]}
    nu[(2, 1)] = nu[(1, 2)] * E[2] / E[1]
    nu[(3, 1)] = nu[(1, 3)] * E[3] / E[1]
    nu[(3, 2)] = nu[(2, 3)] * E[3] / E[2]
    G = {frozenset((1, 2)): p["G12"], frozenset((1, 3)): p["G13"], frozenset((2, 3)): p["G23"]}
    a, b, c = order
    out = {"E1": E[a], "E2": E[b], "E3": E[c], "nu12": nu[(a, b)], "nu13": nu[(a, c)],
           "nu23": nu[(b, c)], "G12": G[frozenset((a, b))], "G13": G[frozenset((a, c))],
           "G23": G[frozenset((b, c))]}
    for k in ("cte", "k"):
        if p.get(k + "1") is not None:
            out[k + "1"], out[k + "2"], out[k + "3"] = p[k + str(a)], p[k + str(b)], p[k + str(c)]
    return out


def _material(f, job: Job, part, tag: str) -> None:
    m = part.material
    p = dict(m.props)
    ori = part.orientation or {}
    f.write(f"*MATERIAL, NAME=M_{tag}\n")
    if m.orthotropic:
        if str(ori.get("system", "rectangular")).lower().startswith("cyl"):
            # CalculiX cylindrical axes: 1 radial, 2 tangential, 3 axial.
            order = tuple(ori.get("map", (3, 1, 2)))   # radial<-thickness, tangential<-1, axial<-2
            p.update(permute_ortho(p, order))
        if job.mechanical:
            f.write("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n")
            f.write(f"{p['E1']:.8g}, {p['E2']:.8g}, {p['E3']:.8g}, {p['nu12']:.8g}, "
                    f"{p['nu13']:.8g}, {p['nu23']:.8g}, {p['G12']:.8g}, {p['G13']:.8g},\n"
                    f"{p['G23']:.8g}\n")
            if p.get("cte1") is not None and job.analysis == "thermal_stress":
                f.write("*EXPANSION, TYPE=ORTHO\n")
                f.write(f"{p['cte1']:.8g}, {p['cte2']:.8g}, {p['cte3']:.8g}\n")
        if job.thermal and p.get("k1") is not None:
            f.write("*CONDUCTIVITY, TYPE=ORTHO\n")
            f.write(f"{p['k1']:.8g}, {p['k2']:.8g}, {p['k3']:.8g}\n")
    else:
        if job.mechanical:
            f.write(f"*ELASTIC\n{p['E']:.8g}, {p['nu']:.8g}\n")
            if p.get("cte") is not None and job.analysis == "thermal_stress":
                f.write(f"*EXPANSION\n{p['cte']:.8g}\n")
            if job.analysis == "nonlinear" and job.opts.get("nonlinear", {}).get("plasticity", True) \
                    and (m.plastic or p.get("yield")):
                f.write("*PLASTIC\n")
                for s, e in m.bilinear_plastic():
                    f.write(f"{s:.8g}, {e:.8g}\n")
        if job.thermal and p.get("k") is not None:
            f.write(f"*CONDUCTIVITY\n{p['k']:.8g}\n")
    if p.get("density") is not None:
        f.write(f"*DENSITY\n{p['density']:.8g}\n")
    if job.thermal and p.get("cp") is not None:
        f.write(f"*SPECIFIC HEAT\n{p['cp']:.8g}\n")


def _orientation(f, job: Job, part, tag: str) -> str:
    ori = part.orientation
    if not ori:
        if part.material.orthotropic:
            f.write(f"*ORIENTATION, NAME=OR_{tag}, SYSTEM=RECTANGULAR\n1., 0., 0., 0., 1., 0.\n")
            return f", ORIENTATION=OR_{tag}"
        return ""
    system = str(ori.get("system", "rectangular")).lower()
    if system.startswith("cyl"):
        o = np.array([job.L(v) for v in ori.get("origin", [0, 0, 0])])
        ax = np.asarray(ori.get("axis", [0, 0, 1]), float)
        if isinstance(ori.get("axis"), str):
            ax = np.eye(3)[AXES[ori["axis"].lower()]]
        b = o + ax / np.linalg.norm(ax)
        f.write(f"*ORIENTATION, NAME=OR_{tag}, SYSTEM=CYLINDRICAL\n")
        f.write(", ".join(f"{v:.8g}" for v in (*o, *b)) + "\n")
    else:
        a = np.asarray(ori.get("a", ori.get("x", [1, 0, 0])), float)
        b = np.asarray(ori.get("b", ori.get("y", [0, 1, 0])), float)
        f.write(f"*ORIENTATION, NAME=OR_{tag}, SYSTEM=RECTANGULAR\n")
        f.write(", ".join(f"{v:.8g}" for v in (*a, *b)) + "\n")
    return f", ORIENTATION=OR_{tag}"


def _moment_forces(mesh: Mesh, fs: FaceSet, M: np.ndarray, about: np.ndarray | None) -> dict[int, np.ndarray]:
    """Nodal forces f_i = w_i (omega x r_i) giving exactly moment M with zero net force."""
    ids = np.array(list(fs.weights))
    w = np.array([fs.weights[i] for i in ids])
    c = (mesh.nodes[ids - 1] * w[:, None]).sum(axis=0) / w.sum()
    r = mesh.nodes[ids - 1] - c
    J = np.zeros((3, 3))
    for wi, ri in zip(w, r):
        J += wi * ((ri @ ri) * np.eye(3) - np.outer(ri, ri))
    omega = np.linalg.lstsq(J, M, rcond=None)[0]
    return {int(i): wi * np.cross(omega, ri) for i, wi, ri in zip(ids, w, r)}


def free_rigid_motions(nodes: np.ndarray, held: np.ndarray) -> list[str]:
    """Rigid-body motions (3 translations, 3 rotations) the held degrees of freedom do not stop.

    A held dof d at node x forbids t_d + (w x x)_d, i.e. the row [e_d, x x e_d] of the 6 rigid modes;
    the supports are enough when those rows span all six."""
    idx, dof = np.nonzero(held)
    if len(idx) == 0:
        return ["move and rotate in every direction (no support at all)"]
    x = nodes[idx]
    c = nodes.mean(axis=0)
    scale = max(float(np.ptp(nodes, axis=0).max()), 1e-9)
    x = (x - c) / scale
    E = np.eye(3)[dof]
    rows = np.hstack([E, np.cross(x, E)])
    w, v = np.linalg.eigh(rows.T @ rows)
    out = []
    for k in np.nonzero(w < 1e-9 * max(w.max(), 1e-30))[0]:
        m = v[:, k]
        t, r = m[:3], m[3:]
        if np.linalg.norm(r) > np.linalg.norm(t):
            out.append("rotate about " + "XYZ"[int(np.argmax(np.abs(r)))])
        else:
            out.append("move along " + "XYZ"[int(np.argmax(np.abs(t)))])
    return list(dict.fromkeys(out))


def minimal_constraint_nodes(mesh: Mesh) -> list[tuple[int, tuple[int, ...]]]:
    """3-2-1 restraint: removes the six rigid-body motions without resisting deformation."""
    lo, _ = mesh.bbox()
    a = mesh.nearest_node(lo)
    pa = mesh.nodes[a - 1]
    d = mesh.nodes - pa
    span = d.max(axis=0) - d.min(axis=0)
    order = np.argsort(-span)                 # longest, middle, shortest axes
    i, j, k = (int(v) for v in order)
    # B: far along i, same j,k as A -> restrain j and k
    score_b = d[:, i] - 10 * (np.abs(d[:, j]) + np.abs(d[:, k]))
    b = int(np.argmax(score_b)) + 1
    # C: far along j, same i,k as A -> restrain k
    score_c = d[:, j] - 10 * (np.abs(d[:, i]) + np.abs(d[:, k]))
    c = int(np.argmax(score_c)) + 1
    return [(a, (1, 2, 3)), (b, (j + 1, k + 1)), (c, (k + 1,))]


def write_deck(job: Job, mesh: Mesh, path: Path) -> dict:
    """Write the deck; return bookkeeping needed for post-processing."""
    info: dict = {"applied_force": [0.0, 0.0, 0.0], "applied_heat": 0.0, "print_sets": [],
                  "thermal_print_sets": [], "constraint_sets": [], "notes": [],
                  "load_summary": []}
    sysname = job.system
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"** EngineeringAgent job: {job.name}\n")
        f.write(f"** Analysis: {job.analysis}\n")
        f.write(f"** UNIT SYSTEM (solver): {U.INTERNAL_BANNER}\n")
        f.write(f"** User unit system: {sysname}\n")
        f.write("*HEADING\n" + job.title[:70] + "\n")
        f.write("*NODE, NSET=NALL\n")
        for i, (x, y, z) in enumerate(mesh.nodes, 1):
            f.write(f"{i}, {x:.9g}, {y:.9g}, {z:.9g}\n")
        f.write(f"*ELEMENT, TYPE={mesh.etype}, ELSET=EALL\n")
        for i, e in enumerate(mesh.elems, 1):
            f.write(f"{i}, " + ", ".join(str(int(n)) for n in e) + "\n")
        for pi, part in enumerate(job.parts):
            ids = mesh.part_elems(part.name)
            f.write(f"*ELSET, ELSET=P_{pi}, GENERATE\n{ids[0]}, {ids[-1]}, 1\n")
        for name, ids in mesh.node_sets.items():
            f.write(f"*NSET, NSET=N_{name}\n")
            _ids(f, ids)
        face_nums: dict[str, list[int]] = {}
        for name, fs in mesh.face_sets.items():
            face_nums[name] = _surface_elsets(f, name, fs)
            f.write(f"*SURFACE, NAME=S_{name}, TYPE=ELEMENT\n")
            for fn in face_nums[name]:
                f.write(f"E_{name}_S{fn}, S{fn}\n")

        # ---- materials and sections
        for pi, part in enumerate(job.parts):
            _material(f, job, part, str(pi))
            ori = _orientation(f, job, part, str(pi))
            f.write(f"*SOLID SECTION, ELSET=P_{pi}, MATERIAL=M_{pi}{ori}\n")

        if job.thermal:
            f.write(f"*PHYSICAL CONSTANTS, ABSOLUTE ZERO={ABS_ZERO}, STEFAN BOLTZMANN={SIGMA_SB:.9g}\n")
            f.write(f"*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, {job.initial_temperature:.8g}\n")

        # ---- interactions
        for k, it in enumerate(job.interactions):
            m, s = it["master"], it["slave"]
            if it["type"] == "tie":
                tol = job.L(it["tolerance"]) if "tolerance" in it else 0.5 * mesh.size
                f.write(f"*TIE, NAME=TIE{k}, POSITION TOLERANCE={tol:.6g}\nS_{s}, S_{m}\n")
            else:
                Emin = min(p.material.get("E") or p.material.get("E3") or 1000.0 for p in job.parts)
                K = job.q(it["stiffness"], "contact_stiffness") if "stiffness" in it else 10.0 * Emin
                f.write(f"*SURFACE INTERACTION, NAME=SI{k}\n")
                f.write(f"*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR\n{K:.6g}\n")
                mu = float(it.get("friction", 0.0))
                if mu > 0:
                    f.write(f"*FRICTION\n{mu:.6g}, {K / 10.0:.6g}\n")
                f.write(f"*CONTACT PAIR, INTERACTION=SI{k}, TYPE=SURFACE TO SURFACE\nS_{s}, S_{m}\n")
                info["notes"].append(f"Contact pair {s}/{m}: linear penalty K={K:.4g} MPa/mm, mu={mu}")

        # ---- amplitudes (time schedules)
        amp_names: dict[int, str] = {}
        def amplitude(item: dict, kind: str) -> str:
            sch = item.get("schedule")
            if not sch:
                return ""
            nm = f"AMP{len(amp_names) + 1}"
            amp_names[id(item)] = nm
            f.write(f"*AMPLITUDE, NAME={nm}\n")
            for t, v in sch:
                f.write(f"{U.to_internal(t, 'time', sysname):.8g}, {U.to_internal(v, kind, sysname):.8g}\n")
            return nm
        for c in job.constraints:
            if c["type"] == "temperature":
                amplitude(c, "temperature")
        for l in job.loads:
            if l["type"] == "convection":
                amplitude(l, "temperature")

        # ---- constraints (model data: active in every step)
        mech = job.mechanical
        bc_lines: list[str] = []
        for c in job.constraints:
            t = c["type"]
            if not mech or t == "temperature":
                continue
            if t == "minimal":
                for nid, dofs in minimal_constraint_nodes(mesh):
                    bc_lines += [f"{nid}, {d}, {d}, 0." for d in dofs]
                info["notes"].append("3-2-1 minimal restraint applied (rigid-body motion only).")
                continue
            on = c["on"]
            if t in ("fixed", "pinned"):
                bc_lines.append(f"N_{on}, 1, 3, 0.")
            elif t == "symmetry":
                d = AXES[str(c.get("normal", "x")).lower()] + 1
                bc_lines.append(f"N_{on}, {d}, {d}, 0.")
            elif t == "displacement":
                for ax, d in (("x", 1), ("y", 2), ("z", 3)):
                    if ax in c and c[ax] is not None and job.L(c[ax]) == 0.0:
                        bc_lines.append(f"N_{on}, {d}, {d}, 0.")
            info["constraint_sets"].append(on)
            if on not in info["print_sets"]:
                info["print_sets"].append(on)
        if bc_lines:
            f.write("*BOUNDARY\n" + "\n".join(bc_lines) + "\n")
        # which translational dofs are held (to account for load applied directly on supports)
        held = np.zeros((mesh.n_nodes, 3), bool)
        for c in job.constraints:
            t = c["type"]
            if not mech or t in ("temperature", "minimal"):
                continue
            idx = mesh.node_sets[c["on"]] - 1
            if t in ("fixed", "pinned"):
                held[idx] = True
            elif t == "symmetry":
                held[idx, AXES[str(c.get("normal", "x")).lower()]] = True
            elif t == "displacement":
                for ax, d in (("x", 0), ("y", 1), ("z", 2)):
                    if ax in c and c[ax] is not None:
                        held[idx, d] = True
        if mech and job.analysis in ("static", "nonlinear", "thermal_stress", "buckling") and \
                not any(c["type"] == "minimal" for c in job.constraints):
            free = free_rigid_motions(mesh.nodes, held)
            if free:                              # a hard stop (owner approved): the AI fixes its supports first
                raise ValueError(
                    "the supports leave the part free to " + " and ".join(free) + " (a rigid-body motion: the "
                    "result may be meaningless). Hold it more: e.g. add `--slide FACE AXIS` on another face, "
                    "or `--slide point:x,y,z AXIS` at a second point away from the first (as in a 3-2-1 support), "
                    "keeping the part free to expand where it should, then run it again")
        on_supports = np.zeros(3)
        sup_nodes = np.nonzero(held.any(axis=1))[0] + 1
        if mech:
            sup_nodes = np.union1d(sup_nodes, [nid for c in job.constraints if c["type"] == "minimal"
                                               for nid, _ in minimal_constraint_nodes(mesh)]).astype(int)
        if len(sup_nodes):
            f.write("*NSET, NSET=N_ALLSUPPORTS\n")
            _ids(f, sup_nodes)
            info["all_supports"] = True

        # ---- step
        a = job.analysis
        nl = job.opts.get("nonlinear", {})
        th = job.opts.get("thermal", {})
        nmodes = int(job.opts.get(a, {}).get("modes", 6 if a == "modal" else 3)) \
            if a in ("modal", "buckling") else 0
        has_contact = any(i["type"] == "contact" for i in job.interactions)
        step_opts = ""
        if a == "nonlinear" and nl.get("nlgeom", True):
            step_opts += ", NLGEOM"
        if a == "nonlinear" or has_contact or job.transient:
            step_opts += f", INC={int(nl.get('max_increments', th.get('max_increments', 2000)))}"
        if job.transient:
            step_opts += ", AMPLITUDE=STEP"
        f.write(f"*STEP{step_opts}\n")
        out_freq = 1
        if a in ("static", "nonlinear"):
            if a == "nonlinear" or has_contact:
                f.write(f"*STATIC\n{nl.get('initial_increment', 0.1)}, 1.0, "
                        f"{nl.get('min_increment', 1e-6)}, {nl.get('max_increment', 0.25)}\n")
                out_freq = 10_000          # last increment only
            else:
                f.write("*STATIC\n")
        elif a == "modal":
            f.write(f"*FREQUENCY\n{nmodes}\n")
        elif a == "buckling":
            f.write(f"*BUCKLE\n{nmodes}\n")
        elif a == "thermal_steady":
            f.write("*HEAT TRANSFER, STEADY STATE\n")
        elif a == "thermal_transient" or (a == "thermal_stress" and job.transient):
            dur = U.to_internal(th.get("duration", 100.0), "time", sysname)
            n = int(th.get("increments", 50))
            dt = U.to_internal(th["time_step"], "time", sysname) if "time_step" in th else dur / n
            proc = "*HEAT TRANSFER" if a == "thermal_transient" else "*UNCOUPLED TEMPERATURE-DISPLACEMENT"
            f.write(f"{proc}, DIRECT\n{dt:.8g}, {dur:.8g}\n")
            nout = int(th.get("frames", 25))
            out_freq = max(1, int(round(dur / dt / nout)))
            info["time_step"], info["duration"] = dt, dur
        elif a == "thermal_stress":
            if job.coupled:
                f.write("*UNCOUPLED TEMPERATURE-DISPLACEMENT, STEADY STATE\n")
            else:
                f.write("*STATIC\n")

        # prescribed non-zero displacements
        for c in job.constraints:
            if c["type"] == "displacement" and mech:
                lines = [(d, job.L(c[ax])) for ax, d in (("x", 1), ("y", 2), ("z", 3))
                         if ax in c and c[ax] is not None and job.L(c[ax]) != 0.0]
                if lines:
                    f.write("*BOUNDARY\n")
                    for d, v in lines:
                        f.write(f"N_{c['on']}, {d}, {d}, {v:.8g}\n")
        # temperature boundary conditions
        if job.thermal and (a != "thermal_stress" or job.coupled):
            for c in job.constraints:
                if c["type"] != "temperature":
                    continue
                amp = amp_names.get(id(c))
                if amp:
                    f.write(f"*BOUNDARY, AMPLITUDE={amp}\nN_{c['on']}, 11, 11, 1.\n")
                else:
                    T = job.q(c["value"], "temperature")
                    f.write(f"*BOUNDARY\nN_{c['on']}, 11, 11, {T:.8g}\n")
                if c["on"] not in info["thermal_print_sets"]:
                    info["thermal_print_sets"].append(c["on"])

        # ---- loads
        cload: dict[int, np.ndarray] = {}
        def add_nodal(forces: dict[int, np.ndarray]):
            for nid, v in forces.items():
                cload[nid] = cload.get(nid, np.zeros(3)) + v
        applied = np.zeros(3)
        dload, film, dflux, radiate, temp_lines = [], [], [], [], []
        for l in job.loads:
            t = l["type"]
            fs = mesh.face_sets.get(l.get("on")) if l.get("on") else None
            if t == "force":
                F = np.array([job.q(v, "force") for v in l["value"]])
                wsum = sum(fs.weights.values())
                add_nodal({n: F * w / wsum for n, w in fs.weights.items()})
                applied += F
                info["load_summary"].append(f"Force {U.fmt_vec(F, 'force', sysname)} on '{l['on']}' "
                                            f"(area {U.fmt(fs.area, 'area', sysname)})")
            elif t in ("moment", "torque"):
                M = np.array([job.q(v, "moment") for v in l["value"]])
                add_nodal(_moment_forces(mesh, fs, M, None))
                info["load_summary"].append(f"Moment {U.fmt_vec(M, 'moment', sysname)} on '{l['on']}'")
            elif t == "pressure":
                p = job.q(l["value"], "pressure")
                for fn in face_nums[l["on"]]:
                    dload.append(f"E_{l['on']}_S{fn}, P{fn}, {p:.8g}")
                # resultant = -p * integral(n dA) from the surface triangles
                pc = mesh.nodes[fs.tris[:, :3] - 1]
                from .mesh import tri_area_vectors
                nA = tri_area_vectors(mesh.nodes, fs.tris)   # true area on curved quadratic faces
                # orient outward using the owning element's opposite corner
                el = fs.elem_faces
                if len(el) == len(nA):
                    cen = mesh.nodes[mesh.elems[el[:, 0] - 1, :4] - 1].mean(axis=1)
                    flip = np.einsum("ij,ij->i", nA, pc.mean(axis=1) - cen) < 0
                    nA[flip] *= -1
                applied += -p * nA.sum(axis=0)
                ld = fs.tris[:, 3:] if mesh.order == 2 else fs.tris       # consistent nodal loads
                share = -p * nA / 3.0
                for col in range(ld.shape[1]):
                    on_supports += (share * held[ld[:, col] - 1]).sum(axis=0)
                info["load_summary"].append(f"Pressure {U.fmt(p, 'pressure', sysname)} on '{l['on']}' "
                                            f"(area {U.fmt(fs.area, 'area', sysname)})")
            elif t == "gravity":
                g = np.asarray(l.get("g", [0, 0, -1]), float)
                mag = float(np.linalg.norm(g))
                if mag > 0:
                    d = g / mag
                    dload.append(f"EALL, GRAV, {mag * G0:.8g}, {d[0]:.8g}, {d[1]:.8g}, {d[2]:.8g}")
                    mass = sum((p.material.get("density") or 0.0) * _part_volume(mesh, p.name)
                               for p in job.parts)
                    applied += mass * G0 * g
                    wts = np.array([-0.05] * 4 + [0.2] * 6) if mesh.order == 2 else np.full(4, 0.25)
                    pe = mesh.nodes[mesh.elems[:, :4] - 1]
                    ev = np.abs(np.einsum("ij,ij->i", pe[:, 1] - pe[:, 0],
                                          np.cross(pe[:, 2] - pe[:, 0], pe[:, 3] - pe[:, 0]))) / 6
                    rho = np.array([p.material.get("density") or 0.0 for p in job.parts])[mesh.elem_part]
                    ew = (ev * rho)[:, None] * G0 * g[None, :]                # element weight vector
                    for col in range(mesh.elems.shape[1]):
                        on_supports += (wts[col] * ew * held[mesh.elems[:, col] - 1]).sum(axis=0)
                    info["load_summary"].append(f"Gravity {mag:g} g along ({d[0]:g}, {d[1]:g}, {d[2]:g})")
            elif t == "centrifugal":
                om = U.to_internal(l.get("speed", l.get("rpm", 0)), "angular_velocity", sysname)
                pt = [job.L(v) for v in l.get("point", [0, 0, 0])]
                d = np.asarray(l.get("axis", [0, 0, 1]), float)
                d /= np.linalg.norm(d)
                dload.append(f"EALL, CENTRIF, {om * om:.8g}, {pt[0]:.8g}, {pt[1]:.8g}, {pt[2]:.8g}, "
                             f"{d[0]:.8g}, {d[1]:.8g}, {d[2]:.8g}")
                info["load_summary"].append(f"Centrifugal load, {om:.4g} rad/s")
                info["unsummed_load"] = "centrifugal"
            elif t == "temperature_change":
                T = job.q(l["value"], "temperature")
                temp_lines.append(f"NALL, {T:.8g}")
                info["load_summary"].append(
                    f"Uniform temperature {U.fmt(T, 'temperature', sysname)} from stress-free "
                    f"{U.fmt(job.initial_temperature, 'temperature', sysname)}")
            elif t == "heat_flux":
                q = job.q(l["value"], "heat_flux")
                for fn in face_nums[l["on"]]:
                    dflux.append(f"E_{l['on']}_S{fn}, S{fn}, {q:.8g}")
                info["applied_heat"] += q * fs.area
                info["load_summary"].append(f"Heat flux {U.fmt(q, 'heat_flux', sysname)} on '{l['on']}'")
            elif t == "heat_power":
                P = job.q(l["value"], "power")
                for fn in face_nums[l["on"]]:
                    dflux.append(f"E_{l['on']}_S{fn}, S{fn}, {P / fs.area:.8g}")
                info["applied_heat"] += P
                info["load_summary"].append(f"Heat input {U.fmt(P, 'power', sysname)} on '{l['on']}'")
            elif t == "heat_generation":
                qv = job.q(l["value"], "heat_gen")
                target = f"P_{[p.name for p in job.parts].index(l['part'])}" if l.get("part") else "EALL"
                dflux.append(f"{target}, BF, {qv:.8g}")
                vol = _part_volume(mesh, l["part"]) if l.get("part") else mesh.volume()
                info["applied_heat"] += qv * vol
                info["load_summary"].append(f"Volumetric heating {U.fmt(qv, 'heat_gen', sysname)}")
            elif t == "convection":
                h = job.q(l["h"], "film")
                amp = amp_names.get(id(l))
                Ta = 1.0 if amp else job.q(l["ambient"], "temperature")
                for fn in face_nums[l["on"]]:
                    film.append((amp, f"E_{l['on']}_S{fn}, F{fn}, {Ta:.8g}, {h:.8g}"))
                info["load_summary"].append(
                    f"Convection h={U.fmt(h, 'film', sysname)} on '{l['on']}', ambient "
                    + ("per schedule" if amp else U.fmt(Ta, 'temperature', sysname)))
            elif t == "radiation":
                Ta = job.q(l["ambient"], "temperature")
                em = float(l.get("emissivity", 0.9))
                for fn in face_nums[l["on"]]:
                    radiate.append(f"E_{l['on']}_S{fn}, R{fn}, {Ta:.8g}, {em:.6g}")
                info["load_summary"].append(
                    f"Radiation emissivity {em:g} on '{l['on']}' to {U.fmt(Ta, 'temperature', sysname)}")
        if temp_lines:
            f.write("*TEMPERATURE\n" + "\n".join(temp_lines) + "\n")
        if cload:
            f.write("*CLOAD\n")
            for nid in sorted(cload):
                for d in range(3):
                    if abs(cload[nid][d]) > 0:
                        f.write(f"{nid}, {d + 1}, {cload[nid][d]:.9g}\n")
        if dload:
            f.write("*DLOAD\n" + "\n".join(dload) + "\n")
        if dflux:
            f.write("*DFLUX\n" + "\n".join(dflux) + "\n")
        for amp in sorted({a_ for a_, _ in film}, key=lambda v: v or ""):
            f.write("*FILM" + (f", AMPLITUDE={amp}" if amp else "") + "\n")
            f.write("\n".join(line for a_, line in film if a_ == amp) + "\n")
        if radiate:
            f.write("*RADIATE\n" + "\n".join(radiate) + "\n")
        for nid, v in cload.items():                       # point forces on held dofs
            on_supports += v * held[nid - 1]
        info["applied_force"] = applied.tolist()
        info["applied_on_supports"] = on_supports.tolist()

        # ---- output requests
        fq = f", FREQUENCY={out_freq}" if out_freq != 1 else ""
        nvars, evars = [], []
        if mech:
            nvars += ["U"] + (["RF"] if a not in ("modal", "buckling") else [])
            evars += ["S"] if a != "buckling" else []
            if a == "nonlinear":
                evars += ["PEEQ"]
            if a in ("static", "nonlinear", "thermal_stress"):
                evars += ["E"]
        if job.thermal and (a != "thermal_stress" or job.coupled):
            nvars += ["NT", "RFL"]
            evars += ["HFL"]
        elif a == "thermal_stress":
            nvars += ["NT"]
        f.write(f"*NODE FILE{fq}\n{', '.join(nvars)}\n")
        if evars:
            f.write(f"*EL FILE{fq}\n{', '.join(evars)}\n")
        if mech and a not in ("modal", "buckling"):
            for s in info["print_sets"] + (["ALLSUPPORTS"] if info.get("all_supports") else []):
                f.write(f"*NODE PRINT, NSET=N_{s}, TOTALS=ONLY{fq}\nRF\n")
        for s in info["thermal_print_sets"]:
            f.write(f"*NODE PRINT, NSET=N_{s}, TOTALS=ONLY{fq}\nRFL\n")
        f.write("*END STEP\n")
    return info


def _part_volume(mesh: Mesh, part: str) -> float:
    sel = mesh.elem_part == mesh.parts.index(part)
    p = mesh.nodes[mesh.elems[sel][:, :4] - 1]
    return float(np.abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0],
                                  np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))).sum() / 6)
