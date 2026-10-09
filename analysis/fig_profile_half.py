"""Upper-half engine profile (gas side, liner, case, C-103 extension) from abeona/cad/engine_profile.csv.

    python3 analysis/fig_profile_half.py      # writes report/figs/fig_profile_half.pdf and .png
"""
import csv, json, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = ['#2a6fdb', '#e8572a', '#2a9d6f', '#8a5cc2', '#7a7a7a', '#d4a017']   # report palette (scripts/plotstyle.py)
matplotlib.rcParams.update({'font.size': 9, 'axes.labelsize': 9, 'axes.titlesize': 10, 'legend.fontsize': 8,
                            'axes.grid': True, 'grid.color': '0.88', 'grid.linewidth': 0.6,
                            'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 300})

lay = json.load(open(os.path.join(ROOT, 'abeona/cad/layout.json')))['engine']
rows = [(float(r['x_mm']) / 1e3, float(r['r_inner_mm']) / 1e3, float(r['r_outer_mm']) / 1e3, r['region'])
        for r in csv.DictReader(open(os.path.join(ROOT, 'abeona/cad/engine_profile.csv')))]
tl, te = lay['liner_thickness'] / 1e3, lay['extension_thickness'] / 1e3
abl = np.array([r[:3] for r in rows if r[3] == 'ablative'])
ext = np.array([r[:3] for r in rows if r[3] != 'ablative'])
ext = np.vstack([[abl[-1, 0], abl[-1, 1], abl[-1, 1] + te], ext])      # extension starts at the attach station
x_a, ri_a, ro_a = abl.T
x_e, ri_e = ext[:, 0], ext[:, 1]
rt, re_ = lay['throat_dia'] / 2e3, lay['exit_dia'] / 2e3

fig, ax = plt.subplots(figsize=(7.5, 3.2))
ax.fill_between(x_a, ri_a, ri_a + tl, color=C[1], alpha=0.35, lw=0, label='silica-phenolic liner, 82.6 mm')
ax.plot(x_a, ro_a, color='0.35', lw=1.8, solid_capstyle='butt', label='Ti-6Al-4V case, 2.5 mm')
ax.plot(x_a, ri_a, color=C[0], lw=1.4, label='gas-side contour (liner)')
ax.plot(x_e, ri_e, color=C[3], lw=2.6, solid_capstyle='butt', label='C-103 extension, 0.6 mm wall')
ax.vlines(x_a[0], ri_a[0], ro_a[0], color='0.35', lw=1.8)
ax.vlines(x_a[-1], ri_a[-1], ro_a[-1], color='0.35', lw=0.8)
ax.axhline(0, color='0.55', lw=0.8, ls='--')
ax.text(x_e[-1], 0.012, 'axis', ha='right', fontsize=7, color='0.4')
ax.axvline(0, color='0.7', lw=0.6, ls=':')
ax.axvline(x_a[-1], color='0.7', lw=0.6, ls=':')
ax.annotate(f'throat $D_t$ = {2*rt*1e3:.1f} mm', (0, rt), (0.12, 0.05), fontsize=8, arrowprops=dict(arrowstyle='-', lw=0.6))
ax.annotate(f'attach, $\\varepsilon$ = 6', (x_a[-1], x_a[-1] * 0 + ri_a[-1] + tl), (0.30, 0.36), fontsize=8,
            arrowprops=dict(arrowstyle='-', lw=0.6))
ax.annotate(f'exit $D_e$ = {2*re_:.3f} m, $\\varepsilon$ = 108', (x_e[-1], ri_e[-1]), (x_e[-1] - 0.62, ri_e[-1] - 0.17),
            fontsize=8, arrowprops=dict(arrowstyle='-', lw=0.6))
ax.text(x_a[0], ri_a[0] + tl + 0.03, 'injector face', fontsize=8)
ax.set_aspect('equal')
ax.set_xlim(x_a[0] - 0.05, x_e[-1] + 0.05)
ax.set_ylim(0, re_ + 0.08)
ax.set_xlabel('axial distance from throat, m')
ax.set_ylabel('radius, m')
ax.legend(loc='lower right', bbox_to_anchor=(1.0, 0.06), frameon=False)
fig.tight_layout()
out = os.path.join(ROOT, 'report/figs/fig_profile_half')
fig.savefig(out + '.pdf'); fig.savefig(out + '.png')
print(out)
