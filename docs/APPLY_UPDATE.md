> Historical 1.x review instructions only. For the complete 2.0 upgrade, use [UPGRADE_2.0_MAC.md](UPGRADE_2.0_MAC.md). Rebuilding only web is insufficient for the new API endpoints.

# Apply this review to your already running app

You reported that the original site opens at localhost:8080 and provider comparison works. Keep that working folder and its `.env`. You do not need to reinstall Docker or regenerate data just to apply this review.

1. Extract the updated ZIP somewhere separate from your working folder.
2. In your existing working folder, replace only `frontend/src/api.ts` with the updated file. This is the application fix. Add `frontend/src/api.test.tsx` for its regression test.
3. Optionally copy the updated `.github/workflows/ci.yml`, the new `scripts/start_mac.sh`, `scripts/check_local.sh`, `scripts/tests/` and the new documentation into the corresponding locations. Keep existing unrelated files. The updated README links to the new guides.
4. Do not replace your entire working folder, `.env`, or Docker volume. This review does not change the database schema, scoring algorithm or Compose services.
5. Open Terminal in your existing working folder. Rebuild and replace only the web service:

```bash
docker compose build web
docker compose up -d --no-deps web
open http://localhost:8080
```

6. Reload the browser and repeat search and comparison. Run the frontend tests from the Mac guide when ready. The fix prevents a slow older search response from replacing newer results.

Your existing Docker Compose project name identifies its containers and volume. Reusing the same original folder avoids accidentally starting a different Compose project. If you use a separate extracted folder instead, first check `docker compose ls` and `docker compose ps -a`; do not start a second copy on the same ports or assume it shares your original data.

Read Lesson 3 of `CareRank_Lab_Beginners_Guide.docx` to begin the page-by-page tour. The setup chapters remain a reference if you later move to another Mac.
