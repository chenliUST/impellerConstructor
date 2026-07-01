# Impeller v0.3 Parameter Sweep Video

This HyperFrames project renders a 1920x1080 MP4 for visual inspection of the current v0.3 `AxisymmetricThroughflowRadialBladedImpeller` runtime.

The generated data and rendered files in this folder are retained as deliberate v0.3 research evidence. Follow `../../docs/evidence-policy.md` before adding more large generated assets.

Output:

- `output/impeller-v03-parameter-sweep.mp4`
- `output/t22-blade-edge-final.png`
- `output/t30-closed-final.png`

Sweep segments:

1. Open impeller profile sweep from about D:H 4:1 to a tall L-shaped hub/tip reference envelope.
2. Open impeller blade-count sweep up to 16 blades.
3. Open impeller blade and edge curve sweep.
4. Closed impeller comparison with finite hood shell visible.

Regenerate data:

```powershell
python scripts/generate_impeller_sweep.py
```

Render:

```powershell
$env:PATH = "$PWD\node_modules\ffmpeg-static;$PWD\node_modules\ffprobe-static\bin\win32\x64;$env:PATH"
npx hyperframes render . --output output/impeller-v03-parameter-sweep.mp4 --fps 30 --quality standard --workers 1
```

Validation used:

```powershell
npx hyperframes lint . --verbose
npx hyperframes validate . --timeout 30000
npx hyperframes inspect . --samples 15 --json
```
