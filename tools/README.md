# Hardware tools

Shared, transport-agnostic inspect, backup, flash and recovery tools.
Targets must supply validated NAND partitions and protected-region policy.
No proprietary vendor binary, factory NAND dump or private credentials in Git.
Existing Windows Amlogic tools will be ported under these boundaries.

## WorldCup/Amlogic tooling custody

Source-only copies of earlier Windows WorldCup detection and backup
experiments are now in tools/amlogic/worldcup/windows. Legacy scripts
still contain Capsula-specific offsets and backup assumptions. The
historical NAND writer is disabled in this location.
Until transport is refactored to use Builder-supplied profiles, the
legacy code MUST NOT be presented as safe universal flash tooling.

The proprietary Amlogic update.exe / update loader and vendor DLLs must
not be committed without license clearance. It can be retrieved separately
by the user from the documented Khadas/OSMC distributions after
checksum verification. NAND dumping is read-only; flashing requires
a validated backup, target partition policy and a tested recovery path.
