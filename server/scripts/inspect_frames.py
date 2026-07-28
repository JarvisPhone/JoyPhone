import json
import re

with open('logs/comm.log') as f:
    content = f.read()

# find all launcher perception lines (skip nodes<50)
pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\|UP\|perception\|(.+)$', re.MULTILINE)
frames = []
for m in pattern.finditer(content):
    ts, payload = m.group(1), m.group(2)
    try:
        obj = json.loads(payload)
    except Exception:
        continue
    if obj.get('pkg') != 'com.android.launcher':
        continue
    nodes = obj.get('nodeTree') or []
    frames.append((ts, obj.get('seq'), nodes))

print(f'total launcher frames: {len(frames)}')

def onscreen_icons(nodes):
    """clickable + w>=100 + h>=100, not smart-card"""
    out = []
    for n in nodes:
        if not n.get('clickable'):
            continue
        b = n.get('bounds')
        if not b:
            continue
        w = b[2]-b[0]
        h = b[3]-b[1]
        if w < 100 or h < 100:
            continue
        rid = n.get('viewIdResourceName') or ''
        if 'instant.card' in rid or 'seedling' in rid:
            continue
        label = (n.get('text') or n.get('desc') or '').strip()
        if label:
            out.append((label, tuple(b)))
    return out

for i, (ts, seq, nodes) in enumerate(frames[:8]):
    icons = onscreen_icons(nodes)
    labels = sorted({lbl for lbl, _ in icons})
    print(f'\n--- Frame #{i} ts={ts} seq={seq} nodes={len(nodes)} icons={len(icons)} ---')
    print(', '.join(labels))
    # any 飞书?
    if any('飞书' in (n.get('text') or n.get('desc') or '') for n in nodes):
        feishu = [n for n in nodes if '飞书' in (n.get('text') or n.get('desc') or '')]
        for n in feishu:
            print(f'  ⚑ 飞书 node id={n["id"]} bounds={n.get("bounds")} clickable={n.get("clickable")} rid={n.get("viewIdResourceName")}')
