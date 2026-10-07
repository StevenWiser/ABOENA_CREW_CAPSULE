"""Build the ABEONA Crew Capsule service-module propulsion system in Onshape (HANDOFF_ONSHAPE.md).

Generates a FeatureScript feature from abeona/cad/engine_profile.csv and abeona/cad/layout.json,
uploads it to a Feature Studio in the document and inserts it into the Part Studio.
The feature has a "Cut view" checkbox that removes the -Y half of every body to show the interior.
Auth: ONSHAPE_ACCESS_KEY / ONSHAPE_SECRET_KEY (HTTP Basic).

    python3 onshape/build_onshape.py            # write onshape/abeona_build.fs, push it, cut view off
    python3 onshape/build_onshape.py --cut      # same, cut view on
"""
import csv, json, math, os, sys
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = 'https://cad.onshape.com/api/v10'
DID, WID = 'ad9a6d4b75d67328be0a01a2', '3973cd08c6897a85595c46d7'
PS_EID = 'bb28d537a3204d397e59d9f9'      # Part Studio 1
FS_EID = '719f4110dafd39880531b4b0'      # Feature Studio "ABEONA build FS"
FS_VERSION = 3083
IN = 25.4

# Densities, kg/m^3. Liner/case/extension/tanks from the report scripts (s06, s09, config);
# injector 304L, lines 321 stainless; head stack, COPVs and regulator panel are lumped to the mass budget (s09).
RHO = dict(liner=1750.0, ti=4430.0, c103=8860.0, ss304=7900.0, ss321=8030.0)
M_HEAD = 14.0 + 20.0 + 10.0              # valves + gimbal actuators + misc, kg (s09)
M_COPV = 379.9394503260619 / 4           # kg each (s09)
M_REG = 10.0                             # regulator / check-valve / filter panel, kg (assumed, part of s09 'components')
CAV_D, CAV_PITCH_R = 16.0, 100.0         # acoustic cavity bore and pitch radius, mm (assumed: not in the design data)

# Tank size from the PDR crew-capsule drawing (PDR_Review slide 7: 2.6 m spheres, 9.203 m^3 each).
# The wall is scaled from s08 (same MEOP and allowable, t ~ D).
TANK_ID = 2600.0
TANK_GAP = 100.0                         # NTO top to MMH bottom (s12)
COPV_WALL = 20.0                         # COPV shell shown hollow for the cut view (lumped density keeps s09 mass)

# Line sizes. Propellant: s08 (1.5 in OD x 0.065 in, 321 SS, ~3.6 m/s at 7.94 kg/s total).
# Helium (sized here): HP 3/8 x 0.065 in (31 MPa, hoop stress 90 MPa, factor 5.7 on 515 MPa ultimate);
# LP 3/4 x 0.049 in (1.33 MPa, ~16 m/s He at the 3.4 L/s per-tank ullage displacement rate).
LINE_PROP = (1.5 * IN / 2, 1.5 * IN / 2 - 0.065 * IN)
LINE_HP = (0.375 * IN / 2, 0.375 * IN / 2 - 0.065 * IN)
LINE_LP = (0.75 * IN / 2, 0.75 * IN / 2 - 0.049 * IN)
Z_ENG_INLET = 500.0                      # propellant inlets on the side of the valve/gimbal stack, mm
NTO_OUTLET_R = 400.0                     # NTO outlet off the bottom pole (the pole sits on the engine stack)
MMH_DROP_X = -1450.0                     # MMH line runs down outside the NTO tank, between the 135/225 deg COPVs
LP_R = 1700.0                            # He LP manifold radius (at +Y, between the 45/135 deg COPVs)
PRESS_PORT_DEG = 60.0                    # pressurization port, angle from the tank top pole

S = requests.Session()
S.auth = (os.environ['ONSHAPE_ACCESS_KEY'], os.environ['ONSHAPE_SECRET_KEY'])
S.headers.update({'Accept': 'application/json;charset=UTF-8; qs=0.09', 'Content-Type': 'application/json'})


def api(method, path, **kw):
    r = S.request(method, API + path, **kw)
    if not r.ok:
        sys.exit(f'{method} {path} -> {r.status_code}: {r.text[:800]}')
    return r.json()


def outlines():
    lay = json.load(open(os.path.join(ROOT, 'abeona/cad/layout.json')))
    rows = [dict(x=float(r['x_mm']), ri=float(r['r_inner_mm']), ro=float(r['r_outer_mm']), reg=r['region'])
            for r in csv.DictReader(open(os.path.join(ROOT, 'abeona/cad/engine_profile.csv')))]
    e = lay['engine']
    zt, tl, te = e['throat_z'], e['liner_thickness'], e['extension_thickness']
    abl = [r for r in rows if r['reg'] == 'ablative']
    ext = [abl[-1]] + [r for r in rows if r['reg'] == 'C103_extension']   # start at the interface station
    z = lambda r: zt - r['x']
    inner = [(r['ri'], z(r)) for r in abl]
    mid = [(r['ri'] + tl, z(r)) for r in abl]
    outer = [(r['ro'], z(r)) for r in abl]

    def annulus(a, b, chamber_line):
        """Closed outline between inner curve a and outer curve b (same stations), as line/spline pieces.
        chamber_line: the first station pair is joined by a straight line (cylindrical chamber section)."""
        k = 1 if chamber_line else 0
        pieces = ([('line', a[:2])] if k else []) + [('spline', a[k:]), ('line', [a[-1], b[-1]]), ('spline', b[k:][::-1])]
        pieces += ([('line', b[:2][::-1])] if k else []) + [('line', [b[0], a[0]])]
        return pieces

    liner = annulus(inner, mid, True)
    case = annulus(mid, outer, True)
    e_in = [(r['ri'], z(r)) for r in ext]
    nozext = e_in                        # gas-side curve only; the extension is this surface thickened by te
    return lay, liner, case, nozext


def layout(lay):
    """Tank, COPV and line positions (mm). Same stacking rules as s12, but each tank sits on its OUTER surface."""
    e, he = lay['engine'], lay['helium_bottles']
    t = {k: lay['tank_' + k]['wall'] * TANK_ID / lay['tank_' + k]['inner_dia'] for k in ('NTO', 'MMH')}
    Ro = {k: TANK_ID / 2 + t[k] for k in t}
    zo = e['gimbal_plane_z'] + Ro['NTO']
    zf = zo + Ro['NTO'] + TANK_GAP + Ro['MMH']
    rcp = he['dia'] / 2
    z_copv = zo + Ro['NTO'] + 50.0
    z_ring = z_copv + rcp + 60.0
    rc = e['chamber_dia'] / 2
    zi = Z_ENG_INLET
    ro_p = LINE_PROP[0]

    # NTO feed: outlet on the lower dome at r = NTO_OUTLET_R, down, then radially into the +X side of the stack
    x_in = NTO_OUTLET_R - ro_p
    z_nto_out = zo - math.sqrt(Ro['NTO'] ** 2 - x_in ** 2)          # lowest dome point under the tube end
    nto = [(NTO_OUTLET_R, 0, z_nto_out), (NTO_OUTLET_R, 0, zi), (rc, 0, zi)]
    # MMH feed: bottom pole, through the tank gap, down outside the NTO tank, into the -X side of the stack
    z_gap = zo + Ro['NTO'] + TANK_GAP / 2
    mmh = [(0, 0, zf - Ro['MMH']), (0, 0, z_gap), (MMH_DROP_X, 0, z_gap), (MMH_DROP_X, 0, zi), (-rc, 0, zi)]

    # He: COPV top outlets -> HP ring -> regulator panel at +Y -> LP lines to each tank's upper dome
    reg_half = (75.0, 75.0, 125.0)
    ang = [math.radians(a) for a in he['angles_deg']]
    hp_stubs = [((he['center_radius'] * math.cos(a), he['center_radius'] * math.sin(a), z_copv + rcp),
                 (he['center_radius'] * math.cos(a), he['center_radius'] * math.sin(a), z_ring)) for a in ang]
    hp_feed = ((0, he['center_radius'], z_ring), (0, LP_R + reg_half[1], z_ring))
    c = math.cos(math.radians(PRESS_PORT_DEG))
    lp = {}
    for k, zc, sgn in (('NTO', zo, -1), ('MMH', zf, +1)):
        zp = zc + Ro[k] * c
        y_end = math.sqrt(Ro[k] ** 2 - (Ro[k] * c - LINE_LP[0]) ** 2)   # tube end just clear of the dome
        z_reg_face = z_ring + sgn * reg_half[2]
        lp[k] = [(0, LP_R, z_reg_face), (0, LP_R, zp), (0, y_end, zp)]
    return dict(t=t, Ro=Ro, zo=zo, zf=zf, z_copv=z_copv, z_ring=z_ring, nto=nto, mmh=mmh, hp_stubs=hp_stubs,
                hp_feed=hp_feed, lp=lp, reg_center=(0, LP_R, z_ring), reg_half=reg_half,
                ullage={k: 1 - v / (math.pi / 6 * (TANK_ID * 1e-3) ** 3) for k, v in (('NTO', 9.080188679245284), ('MMH', 9.056603773584907))},
                clear_top=lay['service_module']['length'] - (zf + Ro['MMH']))


# Capsule + launch escape system outer shape, traced from the PDR review slide-7 drawing (image15.png):
# (pixel row, left-edge column); centreline column 571; 4.98 m = 108 px across, 11.8 m = 265 px tall.
LES_TRACE = dict(
    bullet=[(299, 516), (276, 516), (264, 517), (255, 519), (246, 521), (237, 522.5), (228, 526), (219, 531), (210, 538),
            (204, 543), (198, 549), (195, 552)],
    neck=[(195, 552), (189, 554), (183, 556), (177, 559), (171, 561), (166, 562)],
    rod=[(166, 562), (52, 562)],
    nose=[(52, 562), (50, 563), (46, 564), (43, 565), (36, 568), (33.5, 571)])
LES_WALL = 20.0                          # display shell thickness, mm (no material: reference only)


def les_outline(sm_top):
    sx, sy = 4980.0 / 108, 11800.0 / 265
    pt = lambda y, x: (max(0.0, (571 - x - 1) * sx) if x < 571 else 0.0, sm_top + (299 - y) * sy)
    outer = [[pt(y, x) for y, x in LES_TRACE[k]] for k in ('bullet', 'neck', 'rod', 'nose')]
    outer[0][0] = (4980.0 / 2, sm_top)
    inner = [[(r - LES_WALL, z) for r, z in seg] for seg in outer]
    inner[3] = [(r - LES_WALL, z) for r, z in outer[3][:-2]] + [(0.0, outer[3][-1][1] - 2 * LES_WALL)]
    kinds = ('spline', 'spline', 'line', 'spline')
    pieces = [(k, seg) for k, seg in zip(kinds, outer)]
    pieces.append(('line', [outer[3][-1], inner[3][-1]]))
    pieces += [(k, seg[::-1]) for k, seg in zip(kinds[::-1], inner[::-1])]
    pieces.append(('line', [inner[0][0], outer[0][0]]))
    return pieces


def fs_pieces(pieces):
    return '[' + ', '.join(f'["{k}", {fs_pts(p)}]' for k, p in pieces) + ']'


def fs_pts(pts):
    return '[' + ', '.join('[' + ', '.join(f'{v:.4f}' for v in p) + ']' for p in pts) + ']'


def fs_segs(path):
    return [[path[i], path[i + 1]] for i in range(len(path) - 1)]


def fs_segarr(segs):
    return '[' + ', '.join(fs_pts(s) for s in segs) + ']'


def tube_volume(segs, joints, ro, ri, rings=()):
    """Approximate wall volume of a tube network, mm^3 (for lumped-density checks)."""
    L = sum(math.dist(a, b) for a, b in segs) + sum(2 * math.pi * R for R, _ in rings)
    return math.pi * (ro ** 2 - ri ** 2) * L


def featurescript():
    lay, liner, case, nozext = outlines()
    L = layout(lay)
    e, sm = lay['engine'], lay['service_module']
    rc = e['chamber_dia'] / 2
    z_face, z_gim = e['injector_face_z'], e['gimbal_plane_z']
    z_plate = z_face + e['injector_thickness']
    cav_depth = e['acoustic_cavities']['depth']
    n_cav = e['acoustic_cavities']['n']
    v_cav_head = n_cav * math.pi * (CAV_D / 2) ** 2 * max(0.0, cav_depth - e['injector_thickness'])
    rho_head = M_HEAD / ((math.pi * rc ** 2 * (z_gim - z_plate) - v_cav_head) * 1e-9)
    he = lay['helium_bottles']
    rcp = he['dia'] / 2
    rho_copv = M_COPV / (4 / 3 * math.pi * (rcp ** 3 - (rcp - COPV_WALL) ** 3) * 1e-9)
    hx, hy, hz = L['reg_half']
    rho_reg = M_REG / (8 * hx * hy * hz * 1e-9)
    R, H, Hc = sm['diameter'] / 2, sm['length'], sm['aft_cone_height']
    envelope = [(0.0, -Hc), (200.0, -Hc), (R, 0.0), (R, H), (0.0, H)]   # aft cone to 0.2 m radius (s12 layout figure)
    ss321 = f'material("321 stainless", {RHO["ss321"]} * kilogram / meter ^ 3)'
    ti = f'material("Ti-6Al-4V", {RHO["ti"]} * kilogram / meter ^ 3)'
    rx, ry, rz = L['reg_center']
    lines = []
    for key, name, path, (ro, ri), col in (
            ('feedNTO', 'Feed line - NTO (1.5 in OD x 0.065, 321 SS)', L['nto'], LINE_PROP, 'color(0.85, 0.45, 0.2)'),
            ('feedMMH', 'Feed line - MMH (1.5 in OD x 0.065, 321 SS)', L['mmh'], LINE_PROP, 'color(0.3, 0.6, 0.85)'),
            ('lpNTO', 'He LP line - to NTO tank (0.75 in OD x 0.049, 321 SS)', L['lp']['NTO'], LINE_LP, 'color(0.95, 0.85, 0.2)'),
            ('lpMMH', 'He LP line - to MMH tank (0.75 in OD x 0.049, 321 SS)', L['lp']['MMH'], LINE_LP, 'color(0.95, 0.85, 0.2)')):
        lines.append(f'        tag(context, pipeNet(context, id + "{key}", {fs_segarr(fs_segs(path))}, {fs_pts(path[1:-1])}, [], {ro:.4f}, {ri:.4f}),\n'
                     f'            "{name}", {ss321}, {col});')
    hp_segs = [list(s) for s in L['hp_stubs']] + [list(L['hp_feed'])]
    lines.append(f'        tag(context, pipeNet(context, id + "hp", {fs_segarr(hp_segs)}, [], [[{he["center_radius"]:.4f}, {L["z_ring"]:.4f}]], '
                 f'{LINE_HP[0]:.4f}, {LINE_HP[1]:.4f}),\n'
                 f'            "He HP manifold - COPVs to regulator (0.375 in OD x 0.065, 321 SS)", {ss321}, color(0.95, 0.6, 0.1));')
    tanks = '\n'.join(
        f'        shell(context, id + "tank{k}", {zc:.4f}, {TANK_ID / 2:.4f}, {L["Ro"][k]:.4f}, '
        f'"Tank - {k} (Ti-6Al-4V, 2.6 m ID)", {ti}, {col});'
        for k, zc, col in (('NTO', L['zo'], 'color(0.85, 0.45, 0.2)'), ('MMH', L['zf'], 'color(0.3, 0.6, 0.85)')))
    code = f'''FeatureScript {FS_VERSION};
import(path : "onshape/std/common.fs", version : "{FS_VERSION}.0");

// Generated by onshape/build_onshape.py from abeona/cad/engine_profile.csv and layout.json. Units mm,
// service-module frame: origin at the SM base on the axis, +Z up. Profiles are (r, z) outlines.
const LINER = {fs_pieces(liner)};
const CASE = {fs_pieces(case)};
const EXTENSION = {fs_pts(nozext)};
const LES = {fs_pieces(les_outline(sm['length']))};
const ENVELOPE = {fs_pts(envelope)};
const XZ = plane(vector(0, 0, 0) * millimeter, vector(0, -1, 0), vector(1, 0, 0));   // sketch (u, v) = (X, Z)
const ZAXIS = line(vector(0, 0, 0) * millimeter, vector(0, 0, 1));

function vec(p is array) returns Vector
{{
    return vector(p[0], p[1], p[2]) * millimeter;
}}

function revolveOutline(context is Context, id is Id, pts is array) returns Query
{{
    const sk = newSketchOnPlane(context, id + "sk", {{ "sketchPlane" : XZ }});
    var p = [];
    for (var q in pts)
        p = append(p, vector(q[0], q[1]) * millimeter);
    p = append(p, p[0]);
    skPolyline(sk, "outline", {{ "points" : p }});
    skSolve(sk);
    opRevolve(context, id + "rev", {{ "entities" : qSketchRegion(id + "sk"), "axis" : ZAXIS, "angleForward" : 2 * PI * radian }});
    opDeleteBodies(context, id + "del", {{ "entities" : qCreatedBy(id + "sk") }});
    return qCreatedBy(id + "rev", EntityType.BODY);
}}

// Closed outline of ["line" | "spline", [[r, z], ...]] pieces, revolved 360 deg about Z into one smooth body.
function revolvePieces(context is Context, id is Id, pieces is array) returns Query
{{
    const sk = newSketchOnPlane(context, id + "sk", {{ "sketchPlane" : XZ }});
    for (var i = 0; i < size(pieces); i += 1)
    {{
        var p = [];
        for (var q in pieces[i][1])
            p = append(p, vector(q[0], q[1]) * millimeter);
        if (pieces[i][0] == "line")
            skLineSegment(sk, "l" ~ i, {{ "start" : p[0], "end" : p[1] }});
        else
            skFitSpline(sk, "s" ~ i, {{ "points" : p }});
    }}
    skSolve(sk);
    opRevolve(context, id + "rev", {{ "entities" : qSketchRegion(id + "sk"), "axis" : ZAXIS, "angleForward" : 2 * PI * radian }});
    opDeleteBodies(context, id + "del", {{ "entities" : qCreatedBy(id + "sk") }});
    return qCreatedBy(id + "rev", EntityType.BODY);
}}

// Revolve a fitted spline through pts into a surface and thicken it outward by t (constant wall, one smooth body).
function revolveThicken(context is Context, id is Id, pts is array, t is number) returns Query
{{
    const sk = newSketchOnPlane(context, id + "sk", {{ "sketchPlane" : XZ }});
    var p = [];
    for (var q in pts)
        p = append(p, vector(q[0], q[1]) * millimeter);
    skFitSpline(sk, "s", {{ "points" : p }});
    skSolve(sk);
    opRevolve(context, id + "surf", {{ "entities" : qCreatedBy(id + "sk", EntityType.EDGE), "axis" : ZAXIS, "angleForward" : 2 * PI * radian }});
    opThicken(context, id + "thk", {{ "entities" : qCreatedBy(id + "surf", EntityType.BODY), "thickness1" : t * millimeter, "thickness2" : 0 * millimeter }});
    // thicken must grow away from the gas side: the body's max radius must exceed the largest gas-side radius
    var rmax = 0;
    for (var q in pts)
        rmax = max(rmax, q[0]);
    if (evBox3d(context, {{ "topology" : qCreatedBy(id + "thk", EntityType.BODY) }}).maxCorner[0] < (rmax + t / 2) * millimeter)
    {{
        opDeleteBodies(context, id + "undo", {{ "entities" : qCreatedBy(id + "thk", EntityType.BODY) }});
        opThicken(context, id + "thk2", {{ "entities" : qCreatedBy(id + "surf", EntityType.BODY), "thickness1" : 0 * millimeter, "thickness2" : t * millimeter }});
    }}
    opDeleteBodies(context, id + "del", {{ "entities" : qUnion([qCreatedBy(id + "sk"), qCreatedBy(id + "surf", EntityType.BODY)]) }});
    return qUnion([qCreatedBy(id + "thk", EntityType.BODY), qCreatedBy(id + "thk2", EntityType.BODY)]);
}}

// Hollow tube network: straight segments, spherical elbows at joints, and full rings (radius, z) about the Z axis.
function pipeNet(context is Context, id is Id, segs is array, joints is array, rings is array, ro is number, ri is number) returns Query
{{
    const radii = [ro, ri];
    const tags = ["out", "in"];
    for (var m = 0; m < 2; m += 1)
    {{
        const base = id + tags[m];
        for (var i = 0; i < size(segs); i += 1)
            fCylinder(context, base + ("s" ~ i), {{ "bottomCenter" : vec(segs[i][0]), "topCenter" : vec(segs[i][1]), "radius" : radii[m] * millimeter }});
        for (var i = 0; i < size(joints); i += 1)
            opSphere(context, base + ("j" ~ i), {{ "center" : vec(joints[i]), "radius" : radii[m] * millimeter }});
        for (var i = 0; i < size(rings); i += 1)
        {{
            const sk = newSketchOnPlane(context, base + ("rs" ~ i), {{ "sketchPlane" : XZ }});
            skCircle(sk, "c", {{ "center" : vector(rings[i][0], rings[i][1]) * millimeter, "radius" : radii[m] * millimeter }});
            skSolve(sk);
            opRevolve(context, base + ("r" ~ i), {{ "entities" : qSketchRegion(base + ("rs" ~ i)), "axis" : ZAXIS, "angleForward" : 2 * PI * radian }});
            opDeleteBodies(context, base + ("rd" ~ i), {{ "entities" : qCreatedBy(base + ("rs" ~ i)) }});
        }}
        if (size(evaluateQuery(context, qCreatedBy(base, EntityType.BODY))) > 1)
            opBoolean(context, base + "u", {{ "tools" : qCreatedBy(base, EntityType.BODY), "operationType" : BooleanOperationType.UNION }});
    }}
    opBoolean(context, id + "bore", {{ "tools" : qCreatedBy(id + "in", EntityType.BODY), "targets" : qCreatedBy(id + "out", EntityType.BODY),
                "operationType" : BooleanOperationType.SUBTRACTION }});
    return qCreatedBy(id + "out", EntityType.BODY);
}}

function tag(context is Context, bodies is Query, name is string, mat, col is Color)
{{
    setProperty(context, {{ "entities" : bodies, "propertyType" : PropertyType.NAME, "value" : name }});
    if (mat != undefined)
        setProperty(context, {{ "entities" : bodies, "propertyType" : PropertyType.MATERIAL, "value" : mat }});
    setProperty(context, {{ "entities" : bodies, "propertyType" : PropertyType.APPEARANCE, "value" : col }});
}}

function shell(context is Context, id is Id, zc is number, ri is number, ro is number, name is string, mat, col is Color)
{{
    shellAt(context, id, vector(0, 0, zc) * millimeter, ri, ro);
    tag(context, qCreatedBy(id + "outer", EntityType.BODY), name, mat, col);
}}

function shellAt(context is Context, id is Id, center is Vector, ri is number, ro is number)
{{
    opSphere(context, id + "outer", {{ "center" : center, "radius" : ro * millimeter }});
    opSphere(context, id + "inner", {{ "center" : center, "radius" : ri * millimeter }});
    opBoolean(context, id + "hollow", {{ "tools" : qCreatedBy(id + "inner", EntityType.BODY), "targets" : qCreatedBy(id + "outer", EntityType.BODY),
                "operationType" : BooleanOperationType.SUBTRACTION }});
}}

annotation {{ "Feature Type Name" : "ABEONA engine and tanks" }}
export const abeonaBuild = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {{
        annotation {{ "Name" : "Cut view (remove -Y half)", "Default" : false }}
        definition.cutView is boolean;
    }}
    {{
        // 1. Engine
        tag(context, revolvePieces(context, id + "liner", LINER), "Engine - Ablative liner (silica phenolic)",
            material("Silica phenolic", {RHO["liner"]} * kilogram / meter ^ 3), color(0.45, 0.35, 0.3));
        tag(context, revolvePieces(context, id + "case", CASE), "Engine - Chamber case (Ti-6Al-4V)", {ti}, color(0.7, 0.7, 0.75));
        tag(context, revolveThicken(context, id + "ext", EXTENSION, {e['extension_thickness']}), "Engine - Nozzle extension (C-103)",
            material("C-103 niobium", {RHO["c103"]} * kilogram / meter ^ 3), color(0.35, 0.35, 0.4));
        // trim the thickened extension's end where it meets the liner end face
        opBoolean(context, id + "extTrim", {{ "tools" : qCreatedBy(id + "liner", EntityType.BODY),
                    "targets" : qUnion([qCreatedBy(id + "ext" + "thk", EntityType.BODY), qCreatedBy(id + "ext" + "thk2", EntityType.BODY)]),
                    "operationType" : BooleanOperationType.SUBTRACTION, "keepTools" : true }});
        fCylinder(context, id + "plate", {{ "bottomCenter" : vector(0, 0, {z_face:.4f}) * millimeter, "topCenter" : vector(0, 0, {z_plate:.4f}) * millimeter,
                    "radius" : {rc:.4f} * millimeter }});
        fCylinder(context, id + "head", {{ "bottomCenter" : vector(0, 0, {z_plate:.4f}) * millimeter, "topCenter" : vector(0, 0, {z_gim:.4f}) * millimeter,
                    "radius" : {rc:.4f} * millimeter }});
        var cavs = [];
        for (var i = 0; i < {n_cav}; i += 1)
        {{
            const a = (15 + 360 * i / {n_cav}) * degree;
            fCylinder(context, id + ("cav" ~ i), {{ "bottomCenter" : vector({CAV_PITCH_R} * cos(a), {CAV_PITCH_R} * sin(a), {z_face:.4f}) * millimeter,
                        "topCenter" : vector({CAV_PITCH_R} * cos(a), {CAV_PITCH_R} * sin(a), {z_face + cav_depth:.4f}) * millimeter,
                        "radius" : {CAV_D / 2} * millimeter }});
            cavs = append(cavs, qCreatedBy(id + ("cav" ~ i), EntityType.BODY));
        }}
        opBoolean(context, id + "cavities", {{ "tools" : qUnion(cavs),
                    "targets" : qUnion([qCreatedBy(id + "plate", EntityType.BODY), qCreatedBy(id + "head", EntityType.BODY)]),
                    "operationType" : BooleanOperationType.SUBTRACTION }});
        tag(context, qCreatedBy(id + "plate", EntityType.BODY), "Engine - Injector plate (304L, 12 acoustic cavities)",
            material("304L stainless", {RHO["ss304"]} * kilogram / meter ^ 3), color(0.8, 0.8, 0.82));
        tag(context, qCreatedBy(id + "head", EntityType.BODY), "Engine - Head/valve/gimbal stack (lumped {M_HEAD:.0f} kg)",
            material("Lumped head stack", {rho_head:.3f} * kilogram / meter ^ 3), color(0.55, 0.55, 0.6));

        // 2. Propellant tanks and helium pressurant bottles
{tanks}
        for (var i = 0; i < {he['n']}; i += 1)
        {{
            const ang = {he['angles_deg']}[i];
            const a = ang * degree;
            shellAt(context, id + ("copv" ~ i), vector({he['center_radius']:.4f} * cos(a), {he['center_radius']:.4f} * sin(a), {L['z_copv']:.4f}) * millimeter,
                {rcp - COPV_WALL:.4f}, {rcp:.4f});
            tag(context, qCreatedBy(id + ("copv" ~ i) + "outer", EntityType.BODY), "COPV - He " ~ (i + 1) ~ " (" ~ ang ~ " deg, 31 MPa, lumped {M_COPV:.1f} kg)",
                material("Lumped COPV", {rho_copv:.4f} * kilogram / meter ^ 3), color(0.2, 0.2, 0.2));
        }}

        // 3. Lines: propellant feed (tank outlets to the engine valve inlets) and helium pressurization
{chr(10).join(lines)}
        fCuboid(context, id + "reg", {{ "corner1" : vector({rx - hx:.4f}, {ry - hy:.4f}, {rz - hz:.4f}) * millimeter,
                    "corner2" : vector({rx + hx:.4f}, {ry + hy:.4f}, {rz + hz:.4f}) * millimeter }});
        tag(context, qCreatedBy(id + "reg", EntityType.BODY), "He regulator / check-valve panel (31 to 1.33 MPa, lumped {M_REG:.0f} kg)",
            material("Lumped regulator panel", {rho_reg:.3f} * kilogram / meter ^ 3), color(0.9, 0.2, 0.2));

        // 4. Reference shapes (no material): capsule + LES outer shell from the PDR drawing, SM envelope
        tag(context, revolvePieces(context, id + "les", LES), "REF - Capsule + launch escape system (outer shell)", undefined,
            color(0.75, 0.75, 0.78, 0.35));
        tag(context, revolveOutline(context, id + "env", ENVELOPE), "REF - Service module envelope", undefined, color(0.6, 0.75, 0.95, 0.15));

        // 5. Optional cut view: remove the -Y half of every body
        if (definition.cutView)
        {{
            fCuboid(context, id + "cutBox", {{ "corner1" : vector(-3000, -3000, -3000) * millimeter, "corner2" : vector(3000, 0, 20000) * millimeter }});
            opBoolean(context, id + "cut", {{ "tools" : qCreatedBy(id + "cutBox", EntityType.BODY),
                        "targets" : qSubtraction(qCreatedBy(id, EntityType.BODY), qCreatedBy(id + "cutBox", EntityType.BODY)),
                        "operationType" : BooleanOperationType.SUBTRACTION }});
        }}
    }});
'''
    return code, L


def push(code, cut):
    cur = api('GET', f'/featurestudios/d/{DID}/w/{WID}/e/{FS_EID}')
    if cur['contents'] != code:
        api('POST', f'/featurestudios/d/{DID}/w/{WID}/e/{FS_EID}',
            json=dict(contents=code, serializationVersion=cur['serializationVersion'], sourceMicroversion=cur['sourceMicroversion']))
    return set_feature(cut)


def set_feature(cut):
    mv = next(el['microversionId'] for el in api('GET', f'/documents/d/{DID}/w/{WID}/elements') if el['id'] == FS_EID)
    feats = api('GET', f'/partstudios/d/{DID}/w/{WID}/e/{PS_EID}/features')
    old = [f.get('message', f) for f in feats['features'] if f.get('message', f).get('featureType') == 'abeonaBuild']
    feature = dict(btType='BTMFeature-134', featureType='abeonaBuild', name='ABEONA engine and tanks',
                   namespace=f'e{FS_EID}::m{mv}',
                   parameters=[dict(btType='BTMParameterBoolean-144', parameterId='cutView', value=bool(cut))])
    body = dict(feature=feature, serializationVersion=feats['serializationVersion'], sourceMicroversion=feats['sourceMicroversion'])
    if old:
        feature['featureId'] = old[0]['featureId']
        res = api('POST', f'/partstudios/d/{DID}/w/{WID}/e/{PS_EID}/features/featureid/{old[0]["featureId"]}', json=body)
    else:
        res = api('POST', f'/partstudios/d/{DID}/w/{WID}/e/{PS_EID}/features', json=body)
    return res.get('featureState')


if __name__ == '__main__':
    code, L = featurescript()
    open(os.path.join(ROOT, 'onshape/abeona_build.fs'), 'w').write(code)
    print(json.dumps({k: L[k] for k in ('t', 'Ro', 'zo', 'zf', 'z_copv', 'z_ring', 'ullage', 'clear_top')}, indent=1))
    if '--no-push' not in sys.argv:
        print('feature state:', push(code, '--cut' in sys.argv))
