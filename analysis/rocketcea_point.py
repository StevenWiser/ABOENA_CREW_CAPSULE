"""RocketCEA re-run of the ABEONA design point (report s04 'ideal'), for comparison.

Design point: N2O4/MMH, Pc = 862 kPa, O/F = 1.65, eps = 108, infinite-area combustor.
Frozen = frozen at the chamber (as in the report's eqsolver). Three propellant enthalpy bases:
  default : RocketCEA built-in cards (298.15 K)
  thermo  : report thermo.inp heats of formation (298.15 K)
  report  : thermo.inp + sensible correction to 293.15 K (s04 dh_f, dh_o) -- like-for-like with the report
"""
import json, sys
from rocketcea.cea_obj import add_new_fuel, add_new_oxidizer
from rocketcea.cea_obj_w_units import CEA_Obj

PC, OF, EPS = 862000.0, 1.65, 108.0
G0 = 9.80665
M_MMH, M_NTO = 46.07174, 92.0110                    # g/mol
DH_F, DH_O = -14667.511174143714, -7882.2343049463325  # J/kg, report s04 geom.dh_f / dh_o

REPORT = dict(Tc=3042.306958476358, Mc=20.419299909831707, cstar_s=1737.9344403222406, CF_s=1.9276468701663483,
              Isp_s=341.50090565152607, Pe_s=429.9331372226585, Te_s=768.3682145357548,
              cstar_f=1698.6357301504506, CF_f=1.8752659061933188, Isp_f=324.7088350451513,
              Pe_f=330.6251511064391, Te_f=538.2963506538539)


def cards(tag, h_mmh, h_nto, T):
    add_new_fuel(f'MMH_{tag}', f' fuel CH6N2(L) C 1 H 6 N 2 wt%=100.00\n h,kj/mol={h_mmh/1e3:.4f} t(k)={T}')
    add_new_oxidizer(f'N2O4_{tag}', f' oxid N2O4(L) N 2 O 4 wt%=100.00\n h,kj/mol={h_nto/1e3:.4f} t(k)={T}')
    return f'N2O4_{tag}', f'MMH_{tag}'


def run(ox, fu):
    c = CEA_Obj(oxName=ox, fuelName=fu, pressure_units='Pa', cstar_units='m/s', temperature_units='K',
                isp_units='sec', sonic_velocity_units='m/s')
    out = {}
    Mc, _ = c.get_Chamber_MolWt_gamma(Pc=PC, MR=OF, eps=EPS)
    out['Mc'] = Mc
    for sfx, fz in (('s', 0), ('f', 1)):
        isp, cstar, tc = c.get_IvacCstrTc(Pc=PC, MR=OF, eps=EPS, frozen=fz, frozenAtThroat=0)
        out['Tc'] = tc
        out['cstar_' + sfx] = cstar
        out['Isp_' + sfx] = isp
        out['CF_' + sfx] = isp * G0 / cstar
        out['Pe_' + sfx] = PC / c.get_PcOvPe(Pc=PC, MR=OF, eps=EPS, frozen=fz, frozenAtThroat=0)
        out['Te_' + sfx] = c.get_Temperatures(Pc=PC, MR=OF, eps=EPS, frozen=fz, frozenAtThroat=0)[2]
    return out


cases = {
    'default': run('N2O4', 'MMH'),
    'thermo': run(*cards('th', 54200.0, -17549.0, 298.15)),
    'report': run(*cards('rp', 54200.0 + DH_F * M_MMH / 1e3, -17549.0 + DH_O * M_NTO / 1e3, 293.15)),
}
rows = ['Tc', 'Mc', 'cstar_s', 'CF_s', 'Isp_s', 'Pe_s', 'Te_s', 'cstar_f', 'CF_f', 'Isp_f', 'Pe_f', 'Te_f']
print(f'{"qty":8s}{"report":>11s}' + ''.join(f'{k:>11s}{"d%":>7s}' for k in cases))
for r in rows:
    ref = REPORT[r]
    print(f'{r:8s}{ref:11.4g}' + ''.join(f'{cases[k][r]:11.4g}{(cases[k][r]/ref-1)*100:+7.2f}' for k in cases))
if len(sys.argv) > 1:
    json.dump(dict(design_point=dict(Pc_Pa=PC, OF=OF, eps=EPS), report=REPORT, rocketcea=cases), open(sys.argv[1], 'w'), indent=1)
