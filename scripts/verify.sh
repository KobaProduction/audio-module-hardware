#!/usr/bin/env sh
set -eu
cd "$(git rev-parse --show-toplevel)"
for f in README.md AGENTS.md .gitignore .gitattributes .githooks/pre-push scripts/verify.sh .github/workflows/verify.yml docs/ARCHITECTURE.md builder/build.py builder/profile.py builder/devices/capsula-mini-native/profile.json kernel/platforms/amlogic-a113x.json; do
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
python3 -m compileall -q builder scripts tests
python3 -m unittest discover -s tests -v
# Windows source tests are offline mocks and run cross-platform.
python3 -m unittest discover -s tools/amlogic/worldcup/windows -p 'test_*.py' -v
python3 -m builder.build plan >/dev/null
sh -n scripts/verify.sh
sh -n .githooks/pre-push
sh -n firmware/alpine/overlay/etc/init.d/usbgadget
echo "Hardware source and profile verification passed."
