# Windows Amlogic tooling (source-only)

fast_capture.py monitors the WorldCup USB interface with bounded read-only
identify probes. win_flash.py supports read-only inspection and backup and
contains a historical Capsula Mini partition map. It is not yet a generic
flasher and expects the original author's image layout for its doctor check.

test_fast_capture.py and test_win_flash.py are offline mock tests.

The proprietary backend update.exe and DLLs are deliberately NOT tracked.
The local user's originals and backups are untouched. Before using any tool
against a new board, supply a verified device profile and revise hard-coded
paths and partition definitions; a generic transport cannot infer them.
