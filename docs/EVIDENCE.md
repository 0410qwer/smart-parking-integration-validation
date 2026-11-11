# Evidence included and retained locally

The repository contains sanitized measured test/performance summaries and controlled-trial timings. The final preserved regression was 255 passed, 0 failed, 0 errors, 0 skipped. These are historical observed results, not a claim that a new clone has already rerun them.

Small raw Wokwi Serial fixtures required by the existing tests are intentionally included at their original relative paths. Capture metadata is reduced to browser version, mode and actual control actions; the raw captured Serial bytes are unchanged. The 22-event capture and original supplied firmware retain their validation hashes.

Large screenshots, Playwright traces, raw full-run logs, SQLite databases, process manifests, absolute host paths, historical academic report files and credentials are intentionally omitted. They remain untouched in the original workspace. Archived audit post-processing scripts may require those omitted local archives; they are not prerequisites for running the demo or its regression workflow. Links in the published technical documents point here or to sanitized summaries where original bulky evidence is not uploaded.

`verification-summary.json`, `regression-summary.json` and `controlled-trials.json` are the portable technical evidence. New verification commands generate new ignored local evidence directories; they never recreate a claim of physical hardware or production integration.
