# Validation policy cms-registry-v1

Source identity follows the official CMS National Downloadable File dictionary: NPI + individual enrollment ID + optional group PAC ID + address ID. A blank group is valid when an address is not linked to a group. Do not deduplicate on NPI alone. The resulting stable record key is SHA-256 of a canonical four-element JSON array.

| Rule | Outcome |
|---|---|
| Required selected columns missing or normalized names collide | Entire batch fails; no snapshot |
| Additional unknown columns | Batch warning; column values ignored |
| Missing NPI, enrollment or address ID | Row rejected with finding |
| NPI not 10 digits starting 1/2 | Row rejected; this checks shape, not assignment or NPI checksum |
| Enrollment not 15 alphanumeric characters | Row rejected; conservative local format policy |
| Group PAC nonblank and not 10 digits | Row rejected; blank group accepted |
| Address ID empty or longer than 25 characters | Row rejected; no address geocoding/inferred identity |
| Specialty missing | Warning; accepted if other requirements pass |
| Specialty longer than 60 characters | Row rejected |
| City missing / state missing | Warning for each optional blank |
| City longer than 30 characters, unknown state code, control character | Row rejected |
| Duplicate source identities | Every occurrence rejected, even exact duplicates; no arbitrary winner |
| No valid rows | Entire batch fails; findings retained, no snapshot |
| Empty, malformed CSV or fewer rows than requested | Entire batch fails |
| Interrupted transport, byte/deadline limit or metadata changes during retrieval | Entire batch fails; previous successful snapshots remain |

All seven projected columns must exist even where their values are optional. Known unused source columns (names, phone, street lines, credentials, etc.) are not persisted. API responses expose only selected fields. Failed batches retain audit/findings, not a partially published record set; unpublished raw downloads are not archived. Successful mixed batches retain both accepted and rejected projected rows with per-run findings.

A warning is not a rejected row. One rejected row may have multiple findings. Validation outcomes partition captured rows into valid/rejected; warning totals must not be added to that partition. No rejection-rate threshold is imposed beyond requiring at least one valid row. A succeeded run describes successful processing, not a guarantee that every row is trustworthy or that the source is clinically complete.

Identifiers, source values and checksums are not authenticated by a clinician registry lookup. NPI check digits/assignment are not verified. Cities are not matched to postal databases. State codes include US states, DC, territories, associated states and military codes. New or exceptional CMS values may need policy review. Change POLICY and review cross-version comparability when changing acceptance or identity rules.

The checksum covers canonical selected raw field values in captured row order plus sorted normalized header names. It is **not a checksum of the complete national CSV**, and ignored-field-only changes are intentionally out of scope. Ordered capture matters: row numbers in findings must refer to the stored snapshot's capture order. Comparisons themselves use stable identity, so reordering can create a new capture with zero membership/field changes.

Bounded prefixes can shift between releases. “Removed” means absent from the newer accepted sample, not proven departure from Medicare. An address-key change is a removed/added record, not an inferred move. Missing evidence here is a registry-data validation concern and is never interpreted as low clinical quality.
