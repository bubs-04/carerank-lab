# Public CMS archive boundary

No real CMS archive is bundled: this cloud environment denied the official host with HTTP proxy 403. Do not substitute fixtures and label them CMS.

On an authorized network, capture a bounded public response once, using the existing allowlisted HTTPS connector:

```bash
cd backend
python -m app.ingestion.archive capture ../demo/cms-archive.json --rows 25
python -m app.ingestion.archive verify ../demo/cms-archive.json
```

Review the seven retained fields, official URL, release metadata, capture time and checksum. Names, telephone numbers and street lines are excluded by the connector. Copy the reviewed archive with the demo package; subsequent startup needs no CMS network connection. The checksum detects corruption, not malicious provenance forgery: only distribute operator-reviewed captures. A bounded source-order prefix is not the complete national registry. The archive is imported as CMS with `archive_replay=true` and `fresh_live_retrieval=false`; fixtures and synthetic ranking remain separate.
