"""Upper half of the thrust-chamber contour, same data and style as the report's fig_contour (s05_nozzle.py).

    python3 analysis/fig_profile_half.py <path to abeona/out>   # writes report/figs/fig_profile_half.pdf and .png
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]
C = ['#2a6fdb', '#e8572a', '#2a9d6f', '#8a5cc2', '#7a7a7a', '#d4a017']   # scripts/plotstyle.py
matplotlib.rcParams.update({'font.size': 9, 'axes.titlesize': 10, 'axes.labelsize': 9, 'legend.fontsize': 8,
                            'axes.grid': True, 'grid.color': '0.88', 'grid.linewidth': 0.6,
                            'axes.spines.top': False, 'axes.spines.right': False, 'savefig.dpi': 200})

s5 = json.load(open(os.path.join(OUT, 's05_nozzle.json')))
c6x = json.load(open(os.path.join(OUT, 's06_cooling.json')))['x_att']
X, Y = np.array(s5['contour']['x']), np.array(s5['contour']['y'])
sel = s5['selected']
rt, x_face, Rc = Y.min(), X[0], Y[0]

fig, ax = plt.subplots(figsize=(7.5, 2.4))
ax.plot(X, Y, color=C[0], lw=2)
ax.axhline(0, color='0.6', lw=0.8, ls='--')
ax.axvline(0, color='0.75', lw=0.6, ls=':')
ax.annotate(f'throat: Dt {2*rt*1e3:.1f} mm', (0, rt), (0.25, 0.15), arrowprops=dict(arrowstyle='-', lw=0.6))
ax.annotate(f'exit: De {sel["De"]:.2f} m, θE {sel["thE"]:.1f}°', (X[-1], Y[-1]), (X[-1] - 0.70, Y[-1] - 0.36))
ax.text(x_face - 0.05, Rc + 0.12, 'injector face', fontsize=8)
ax.set_aspect('equal')
ax.set_ylim(0, None)
ax.set_xlabel('axial distance from throat, m')
ax.set_ylabel('radius, m')
ax.set_title(f'Thrust-chamber contour, Rao bell (θN {sel["thN"]:.1f}°, ε 108, 80 %)')
ax.axvline(c6x, color='0.6', ls=':', lw=0.8)
ax.text(c6x + 0.03, 0.03, 'ablative | C-103', fontsize=7)
fig.tight_layout()
out = os.path.join(ROOT, 'report/figs/fig_profile_half')
fig.savefig(out + '.pdf'); fig.savefig(out + '.png')
print(out)
