# Beside recovery: please document any recurrence

One earlier Beside run was reported to remove the donor while writing the new,
collision-renamed output. The original remained visible as a cached grid card.
The cause was not established. After a restart, repeated Beside -> Replace of the
new sibling -> Beside tests preserved the originals. A separate missing recovery
helper was diagnosed and repaired later; it is not a confirmed cause of this report.

Current Beside recovery uses a separate sibling target, refuses source aliases,
and verifies donor file identity. This is not a claim that the historical incident
has been reproduced or conclusively fixed.

If it recurs, open a GitHub bug report and include:

- N8Vision version and the sequence of Beside/Replace/Output runs, including restarts.
- The selected destination for the failing run.
- Donor and returned output paths (redact personal folder names if needed).
- Whether each file exists on disk, versus only appearing in the grid.
- Console lines showing recovery mode, donor, output, and any error.

Do not include credentials. Recovery of the earlier disposable donor was not
requested; this issue tracks any future reproducible recurrence.
