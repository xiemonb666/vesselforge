# Checker receipts

Transcribed from tool returns; raw stdout/stderr bytes NOT_PERSISTED. No rerun.

CWD: `C:\Users\xiemo\Desktop\ShardForge`. Args after interpreter: `vesselforge/tmp/review_20261006/exact_curvature_certificate_independent/check_certificate.py vesselforge/tmp/review_20261006/exact_curvature_certificate_20261006/exact_curvature_certificate.json b08a550d14e59ed9945408bafc42a921692f1ef7f9c4540dc77f8a364ede8bde`.

1. `C:\Users\xiemo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` + args (no `-B`): rc 0, 261.614 ms; output `PASS: exact_curvature_certificate.json; independent exact checks passed; nodes=82`. Posthoc exe SHA: `372c2eae555b344520bf147be0096e009069aeca4e7f78d6aecea6d53158056a`.
2. `C:\Users\xiemo\Desktop\ShardForge\third_party\vesselforge-runtime\venv\Scripts\python.exe -B` + args: rc 0, 262.011 ms; same output. Posthoc exe SHA: `2b83f3f84ea2f51132fa1aae73815be54126a799521de85ff6ea70627cde6da7`.

Both runs: pre/post SHA identical: checker `8a8ca7d75349d6d1475356b9ed026bd43f0934a7cc7ffabc1edd83c69a52a593`; certificate `b08a550d14e59ed9945408bafc42a921692f1ef7f9c4540dc77f8a364ede8bde`; cases `e1e9c3cf659dbc59d99a18c4b70694201518be4f3aba09a57806402e732cf95a`; profile `057233b930a2b8e0e3ef43a3568f1cb0e6e972baed97eeeeceb6459d9de8c951`; diagnostic `eb60138fc559d5a06ab2b4febf82fdc6654e6bbeab84f05f847c65934ffbbd4f`.

Bare `python` launch resolved to `C:\Users\xiemo\AppData\Local\Microsoft\WindowsApps\python.exe`; rc 9009, 109.812 ms. Returned: `Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.` Checker did not start; PowerShell wrapper rc 0. Successful elapsed sum: 523.625 ms.

Review: exact certificate checks passed (82 nodes). Jar shoulder fails only the sufficient `|3κ|<1` bound; `D<0`, `κ≈−0.3587`, inward factor≈2.076>0, so signed regularity is UNKNOWN. No physical/global/CAD claim.
