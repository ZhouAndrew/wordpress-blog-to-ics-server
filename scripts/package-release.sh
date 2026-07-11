#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="wordpress-blog-to-ics-server"
RELEASE_BRANCH="${RELEASE_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python}"

usage() {
    cat <<'EOF'
Usage:
  ./scripts/package-release.sh <version> [git-ref]

Examples:
  # Package the current HEAD as a release candidate:
  ./scripts/package-release.sh v0.1.0-alpha

  # Package an existing release tag:
  ./scripts/package-release.sh v0.1.0-alpha v0.1.0-alpha

Environment variables:
  RELEASE_BRANCH   Required release branch. Default: main
  PYTHON_BIN       Python executable. Default: python
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

info() {
    echo
    echo "==> $*"
}

VERSION="${1:-}"
REF="${2:-HEAD}"

if [[ -z "$VERSION" ]]; then
    usage
    exit 2
fi

if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
    fail "Invalid version format: $VERSION"
fi

# ---------------------------------------------------------------------------
# Locate repository
# ---------------------------------------------------------------------------

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || fail "Not inside a Git repository."

cd "$REPO_ROOT"

DIST_DIR="$REPO_ROOT/dist"

TAR_FILE="$DIST_DIR/${PROJECT_NAME}-${VERSION}.tar.gz"
ZIP_FILE="$DIST_DIR/${PROJECT_NAME}-${VERSION}.zip"
CHECKSUM_FILE="$DIST_DIR/SHA256SUMS"
METADATA_FILE="$DIST_DIR/RELEASE-METADATA.txt"

# ---------------------------------------------------------------------------
# Repository checks
# ---------------------------------------------------------------------------

info "Checking Git repository"

CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" != "$RELEASE_BRANCH" ]]; then
    fail "Release packaging must run from '$RELEASE_BRANCH'; current branch is '$CURRENT_BRANCH'."
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo
    git status --short
    echo
    fail "Working tree is not clean."
fi

if ! git rev-parse --verify "$REF^{commit}" >/dev/null 2>&1; then
    fail "Git ref does not exist: $REF"
fi

PACKAGE_COMMIT="$(git rev-parse "$REF^{commit}")"
HEAD_COMMIT="$(git rev-parse HEAD)"

echo "Project : $PROJECT_NAME"
echo "Version : $VERSION"
echo "Branch  : $CURRENT_BRANCH"
echo "Ref     : $REF"
echo "Commit  : $PACKAGE_COMMIT"

# If packaging HEAD, make sure it is the current commit.
if [[ "$REF" == "HEAD" && "$PACKAGE_COMMIT" != "$HEAD_COMMIT" ]]; then
    fail "HEAD resolution mismatch."
fi

# If origin/main exists locally, ensure HEAD matches it.
if git show-ref --verify --quiet "refs/remotes/origin/${RELEASE_BRANCH}"; then
    ORIGIN_COMMIT="$(git rev-parse "origin/${RELEASE_BRANCH}")"

    if [[ "$HEAD_COMMIT" != "$ORIGIN_COMMIT" ]]; then
        fail "HEAD does not match origin/${RELEASE_BRANCH}. Pull or push changes first."
    fi

    echo "Remote  : origin/${RELEASE_BRANCH} matches HEAD"
else
    echo "Warning : origin/${RELEASE_BRANCH} is not available locally; remote equality check skipped."
fi

# ---------------------------------------------------------------------------
# Repository hygiene / secrets check
# ---------------------------------------------------------------------------

info "Checking repository hygiene"

FORBIDDEN_TRACKED="$(
    git ls-files |
    grep -E '(^|/)(config\.json|secrets\.json|.*\.secrets\.json|.*\.token|.*\.tokens)$' \
    || true
)"

if [[ -n "$FORBIDDEN_TRACKED" ]]; then
    echo "$FORBIDDEN_TRACKED" >&2
    fail "Forbidden runtime or secret files are tracked by Git."
fi

echo "No forbidden config or secret files are tracked."

# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

info "Checking Python and pytest"

command -v "$PYTHON_BIN" >/dev/null 2>&1 \
    || fail "Python executable not found: $PYTHON_BIN"

if ! "$PYTHON_BIN" -c 'import pytest' >/dev/null 2>&1; then
    fail "pytest is not installed for '$PYTHON_BIN'. Activate the development virtual environment first."
fi

echo "Python: $("$PYTHON_BIN" --version 2>&1)"

info "Running full test suite"

"$PYTHON_BIN" -m pytest -q

# ---------------------------------------------------------------------------
# Build release archives
# ---------------------------------------------------------------------------

info "Creating release archives"

mkdir -p "$DIST_DIR"

rm -f \
    "$TAR_FILE" \
    "$ZIP_FILE" \
    "$CHECKSUM_FILE" \
    "$METADATA_FILE"

ARCHIVE_PREFIX="${PROJECT_NAME}-${VERSION}/"

git archive \
    --format=tar.gz \
    --prefix="$ARCHIVE_PREFIX" \
    --output="$TAR_FILE" \
    "$REF"

git archive \
    --format=zip \
    --prefix="$ARCHIVE_PREFIX" \
    --output="$ZIP_FILE" \
    "$REF"

# ---------------------------------------------------------------------------
# Verify package contents
# ---------------------------------------------------------------------------

info "Verifying package contents"

FORBIDDEN_ARCHIVE_ENTRIES="$(
    tar -tzf "$TAR_FILE" |
    grep -E '(^|/)(config\.json|secrets\.json|.*\.secrets\.json|.*\.token|.*\.tokens)$' \
    || true
)"

if [[ -n "$FORBIDDEN_ARCHIVE_ENTRIES" ]]; then
    echo "$FORBIDDEN_ARCHIVE_ENTRIES" >&2
    rm -f "$TAR_FILE" "$ZIP_FILE"
    fail "Release archive contains forbidden config or secret files."
fi

echo "Archive hygiene check passed."

# ---------------------------------------------------------------------------
# Release metadata
# ---------------------------------------------------------------------------

info "Writing release metadata"

{
    echo "Project: $PROJECT_NAME"
    echo "Version: $VERSION"
    echo "Git ref: $REF"
    echo "Commit: $PACKAGE_COMMIT"
    echo "Branch: $CURRENT_BRANCH"
    echo "Created UTC: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "Python: $("$PYTHON_BIN" --version 2>&1)"
} > "$METADATA_FILE"

# ---------------------------------------------------------------------------
# SHA256 checksums
# ---------------------------------------------------------------------------

info "Generating SHA256 checksums"

(
    cd "$DIST_DIR"
    sha256sum \
        "$(basename "$TAR_FILE")" \
        "$(basename "$ZIP_FILE")" \
        "$(basename "$METADATA_FILE")" \
        > "$(basename "$CHECKSUM_FILE")"
)

# Verify checksums immediately.
(
    cd "$DIST_DIR"
    sha256sum -c "$(basename "$CHECKSUM_FILE")"
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

info "Release package completed successfully"

echo
echo "Version : $VERSION"
echo "Ref     : $REF"
echo "Commit  : $PACKAGE_COMMIT"
echo
echo "Artifacts:"
echo "  $TAR_FILE"
echo "  $ZIP_FILE"
echo "  $CHECKSUM_FILE"
echo "  $METADATA_FILE"
echo
echo "Next step for a release candidate:"
echo "  Extract the archive into a clean directory and run ./install.sh"
echo
echo "Next step for an existing tag:"
echo "  gh release create $VERSION \\"
echo "    \"$TAR_FILE\" \\"
echo "    \"$ZIP_FILE\" \\"
echo "    \"$CHECKSUM_FILE\" \\"
echo "    \"$METADATA_FILE\" \\"
echo "    --title \"$PROJECT_NAME $VERSION\" \\"
echo "    --prerelease \\"
echo "    --verify-tag"
