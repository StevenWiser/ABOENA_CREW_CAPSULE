"""Mass properties, interference check and screenshots for the ABEONA Part Studio.

    python3 onshape/verify_onshape.py          # writes onshape/results.json and onshape/screenshots/*.png
"""
import base64, json, os
from build_onshape import api, DID, WID, PS_EID, ROOT

PS = f'/partstudios/d/{DID}/w/{WID}/e/{PS_EID}'
OUT = os.path.join(ROOT, 'onshape')

# Pairwise intersection volumes on copies of the bodies (the evaluation context is discarded), plus the
# volume of each hardware part lying outside the service-module envelope.
CHECK = '''function(context is Context, queries) {
    var bodies = evaluateQuery(context, qAllModifiableSolidBodies());
    var names = [];
    var env;
    var hw = [];
    for (var b in bodies) {
        const n = getProperty(context, { "entity" : b, "propertyType" : PropertyType.NAME });
        if (n == "REF - Service module envelope") env = b; else { hw = append(hw, b); names = append(names, n); }
    }
    const overlap = function(tag is string, a is Query, b is Query, op is string) {
        const id = makeId("chk" ~ tag);
        opPattern(context, id + "a", { "entities" : a, "transforms" : [identityTransform()], "instanceNames" : ["a"] });
        opPattern(context, id + "b", { "entities" : b, "transforms" : [identityTransform()], "instanceNames" : ["b"] });
        const ca = qCreatedBy(id + "a", EntityType.BODY);
        const cb = qCreatedBy(id + "b", EntityType.BODY);
        var v = 0 * meter ^ 3;
        try silent {
            if (op == "int")
                opBoolean(context, id + "op", { "tools" : qUnion([ca, cb]), "operationType" : BooleanOperationType.INTERSECTION });
            else
                opBoolean(context, id + "op", { "tools" : cb, "targets" : ca, "operationType" : BooleanOperationType.SUBTRACTION });
            const left = qUnion([qCreatedBy(id + "a", EntityType.BODY), qCreatedBy(id + "b", EntityType.BODY), qCreatedBy(id + "op", EntityType.BODY)]);
            if (size(evaluateQuery(context, left)) > 0)
                v = evVolume(context, { "entities" : left });
        }
        try silent { opDeleteBodies(context, id + "del", { "entities" : qUnion([qCreatedBy(id + "a"), qCreatedBy(id + "b"), qCreatedBy(id + "op")]) }); }
        return v / millimeter ^ 3;
    };
    var pairs = [];
    for (var i = 0; i < size(hw); i += 1)
        for (var j = i + 1; j < size(hw); j += 1) {
            const v = overlap(i ~ "x" ~ j, hw[i], hw[j], "int");
            const d = evDistance(context, { "side0" : hw[i], "side1" : hw[j] }).distance / millimeter;
            pairs = append(pairs, { "a" : names[i], "b" : names[j], "overlap_mm3" : v, "min_distance_mm" : d });
        }
    var outside = [];
    for (var i = 0; i < size(hw); i += 1)
        outside = append(outside, { "part" : names[i], "outside_envelope_mm3" : overlap("env" ~ i, hw[i], env, "sub") });
    return { "pairs" : pairs, "outside" : outside };
}'''

VIEWS = {  # 3x4 view matrices (row-major rotation, then translation)
    'iso': '0.707,0.707,0,0,-0.408,0.408,0.816,0,0.577,-0.577,0.577,0',
    'front': '1,0,0,0,0,0,1,0,0,-1,0,0',
}


def unwrap(v):
    """Convert the BTFSValue JSON tree returned by the FeatureScript endpoint to plain Python."""
    if not isinstance(v, dict) or 'btType' not in v:
        return v
    t, val = v['btType'], v.get('value')
    if t.endswith('BTFSValueMap'):
        return {unwrap(e['key']): unwrap(e['value']) for e in val}
    if t.endswith('BTFSValueArray'):
        return [unwrap(e) for e in val]
    return val


if __name__ == '__main__':
    parts = api('GET', f'/parts/d/{DID}/w/{WID}/e/{PS_EID}')
    mp = api('GET', PS + '/massproperties', params=dict(massAsGroup='false', useMassPropertyOverrides='false'))['bodies']
    res = dict(parts=[])
    for p in parts:
        b = mp.get(p['partId'], {})
        res['parts'].append(dict(name=p['name'], partId=p['partId'], material=(p.get('material') or {}).get('displayName'),
                                 mass_kg=b.get('mass', [None, None])[1] if b.get('hasMass') else None,
                                 volume_m3=b.get('volume', [None, None])[1],
                                 centroid_z_mm=b['centroid'][2] * 1e3 if b.get('centroid') else None))
    fs = api('POST', PS + '/featurescript', json=dict(script=CHECK))
    if fs.get('notices'):
        print('notices:', json.dumps(fs['notices'])[:1500])
    res['interference'] = unwrap(fs['result'])
    json.dump(res, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
    for p in res['parts']:
        print(f"{p['name']:60s} {p['material'] or '-':20s} m={p['mass_kg'] if p['mass_kg'] is None else round(p['mass_kg'], 2)} kg"
              f"  zc={p['centroid_z_mm']:.0f} mm")
    os.makedirs(os.path.join(OUT, 'screenshots'), exist_ok=True)
    for name, vm in VIEWS.items():
        img = api('GET', PS + '/shadedviews', params=dict(viewMatrix=vm, outputHeight=1200, outputWidth=900, pixelSize=0, edges='show'))
        open(os.path.join(OUT, f'screenshots/{name}.png'), 'wb').write(base64.b64decode(img['images'][0]))
