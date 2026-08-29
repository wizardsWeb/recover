# Demo video

The recording itself is not in the repository. The capture is 464 MB — 2304×1440
at 60 fps — and GitHub rejects any file over 100 MB, so it is hosted and linked
from the root README instead.

`demo.mp4` sits here locally and is gitignored.

To regenerate it from scratch:

```bash
cd frontend
npx playwright test selector-check --project=demo   # 80s pre-flight
npm run demo:capture                                # 60fps screen capture
```

The narration is built separately — see `docs/voiceover/`.
