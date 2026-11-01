#!/usr/bin/env sh
set -eu
cd "$(git rev-parse --show-toplevel)"
for f in README.md AGENTS.md .gitignore .gitattributes .githooks/pre-push scripts/verify.sh .github/workflows/verify.yml docs/ARCHITECTURE.md docs/HAL_CONTRACT.md docs/UPDATES.md docs/PERSISTENCE.md docs/STORAGE_LAYOUT.md docs/ARCHITECTURE_REFERENCES.md uboot/IDENTITY.md uboot/env_audit.py firmware/storage/README.md builder/build.py builder/input_attestation.py builder/profile.py builder/kernel_config.py builder/kernel_source.py builder/storage.py builder/devices/capsula-mini-native/storage.json builder/devices/capsula-mini-native/profile.json builder/devices/capsula-mini-native/capabilities.json builder/devices/capsula-mini-native/persistence.json kernel/platforms/amlogic-a113x.json kernel/patches/amlogic-a113x/0001-capsula-mini-board-names.patch hal/manifest.py hal/probe.py firmware/updates/check.py firmware/updates/persistence.py; do
    test -s "$f" || { echo "Missing expected bootstrap: $f" >&2; exit 1; }
done
empty_tree="$(git hash-object -t tree /dev/null)"
git diff --check "$empty_tree" HEAD
git diff --check --cached
# Reject secret / device-dump paths even if someone force-adds them.
git ls-files --cached --others --exclude-standard | while IFS= read -r path; do
    case "$path" in
       *.pem|*.key|*.ppk|*.exe|*.dll|*.raw.bin|*/backups/*|backups/*|*/device-dumps/*|device-dumps/*|*/.env|.env)
           echo "Private artifact cannot be tracked: $path" >&2; exit 1 ;;
    esac
done
python3 -m compileall -q builder hal firmware uboot scripts tests tools/diagnostics
python3 -m unittest discover -s tests -v
# Windows source tests are offline mocks and run cross-platform.
python3 -m unittest discover -s tools/amlogic/worldcup/windows -p 'test_*.py' -v
python3 -m builder.build plan >/dev/null
python3 -m firmware.updates.check --help >/dev/null
sh -n scripts/verify.sh
sh -n .githooks/pre-push
sh -n firmware/alpine/overlay/etc/init.d/usbgadget
echo "Hardware source and profile verification passed."
