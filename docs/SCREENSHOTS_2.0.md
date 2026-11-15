# Capture real 2.0 screenshots

No screenshots are bundled: Chrome aborted before opening a page in the delivery environment. These instructions produce actual app screenshots, not mockups.

After applying the safe upgrade and checking http://localhost:8080:

```bash
cd frontend
npm ci
npx playwright install chromium
BASE_URL=http://localhost:8080 npm run e2e
cd ..
```

| File | View |
|---|---|
| `docs/overview.png` | Overview metrics and charts |
| `docs/analytics.png` | Cardiology scatter and evidence dashboard |
| `docs/explorer.png` | Filtered Provider Explorer with selection |
| `docs/provider-profile.png` | Existing profile and score evidence |
| `docs/comparison.png` | Grouped component chart plus detailed profiles |
| `docs/mobile.png` | 390 × 844 mobile Overview |
| `docs/mobile-analytics.png` | 390 × 844 mobile Analytics |

Tests require the default specialties and a nontrivial eligible cohort. They never reseed the database. Inspect the actual PNGs for clipping, legibility, tooltip/focus behavior and unintended personal information before publication. The CI artifact configuration includes every path above, but no remote CI run has happened yet.

After successful capture, add these lines to the README's Screenshots section:

```markdown
![Overview](docs/overview.png)
![Analytics](docs/analytics.png)
![Provider Explorer](docs/explorer.png)
![Provider profile](docs/provider-profile.png)
![Comparison](docs/comparison.png)
![Mobile analytics](docs/mobile-analytics.png)
```

Do not add those image references before the files exist. If the browser fails, retain the actual failure output and leave the screenshot section transparent.
