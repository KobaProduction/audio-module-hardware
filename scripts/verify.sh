#!/usr/bin/env sh
set -eu

cd "$(git rev-parse --show-toplevel)"

for required in README.md AGENTS.md .gitignore .gitattributes .githooks/pre-push scripts/verify.sh .github/workflows/verify.yml; do
    if [ ! -s "$required" ]; then
        echo "ERROR: missing or empty repository bootstrap file: $required" >&2
        exit 1
    fi
done

# Verify the complete repository tree, including the initial root commit.
empty_tree="$(git hash-object -t tree /dev/null)"
git diff --check "$empty_tree" HEAD
git diff --check --cached

# Prevent committing private device data or authentication material.
git ls-files | while IFS= read -r path; do
    case "$path" in
        *.pem|*.key|*.ppk|*.raw.bin|*/backups/*|backups/*|*/device-dumps/*|device-dumps/*|*/.env|.env)
            echo "ERROR: sensitive file is tracked: $path" >&2
            exit 1
            ;;
        *.py|*.ts|*.tsx|*.c|*.cc|*.cpp|*.h|*.hpp|*.rs|*.go|*.dts|*.dtsi)
            echo "ERROR: source present but language toolchain verification is not configured: $path" >&2
            exit 1
            ;;
    esac
done

echo "Bootstrap verification passed (docs-only)."
