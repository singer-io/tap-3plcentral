#!/usr/bin/env bash
#
# Run tap-3plcentral integration tests using tap-tester with a local mock API server.
#
# Usage:
#   ./tests/run_tests.sh                                          # run all test files
#   ./tests/run_tests.sh test_discovery.py                        # run a specific test
#   ./tests/run_tests.sh test_bookmark.py test_start_date.py      # run multiple tests
#
# Environment variables (all have safe defaults for mock testing):
#   MOCK_SERVER_PORT       — port for the mock API server  (default: 8765)
#   TAP_3PLCENTRAL_BASE_URL  — override base URL           (auto-set to mock)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TAP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- configuration ---
MOCK_PORT="${MOCK_SERVER_PORT:-8765}"
MOCK_URL="http://localhost:${MOCK_PORT}"
TAP_TESTER_VENV="/usr/local/share/virtualenvs/tap-tester"
TAP_VENV="/usr/local/share/virtualenvs/tap-3plcentral"
TAP_TESTER_DIR="/opt/code/tap-tester"

# --- export environment for the tap ---
export TZ=UTC
export TAP_3PLCENTRAL_BASE_URL="${MOCK_URL}"
export TAP_3PLCENTRAL_CLIENT_ID="mock_client_id"
export TAP_3PLCENTRAL_CLIENT_SECRET="mock_client_secret"
export TAP_3PLCENTRAL_TPL_KEY="mock_tpl_key"
export TAP_3PLCENTRAL_USER_LOGIN_ID="1"
export TAP_3PLCENTRAL_USER_AGENT="tap-3plcentral <test@test.com>"
export TAP_3PLCENTRAL_CUSTOMER_ID="50"
export TAP_3PLCENTRAL_FACILITY_ID="1"

# --- kill any leftover mock server on the port ---
fuser -k "${MOCK_PORT}/tcp" 2>/dev/null || true
sleep 0.5

# --- start mock server ---
echo "▶ Starting mock 3PLCentral API server on port ${MOCK_PORT}…"
"${TAP_VENV}/bin/python" "${SCRIPT_DIR}/mock_server.py" --port "${MOCK_PORT}" &
MOCK_PID=$!

# give the server a moment to bind
sleep 1

# make sure we stop it no matter what
cleanup() {
    echo "▶ Stopping mock server (PID ${MOCK_PID})…"
    kill "${MOCK_PID}" 2>/dev/null || true
    wait "${MOCK_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# quick health-check
if ! curl -sf "${MOCK_URL}/customers?pgnum=1&pgsiz=1" >/dev/null; then
    echo "✗ Mock server did not start correctly." >&2
    exit 1
fi
echo "✓ Mock server is healthy."

# --- activate tap-tester venv ---
# shellcheck disable=SC1091
source "${TAP_TESTER_VENV}/bin/activate"

# --- determine which tests to run ---
if [[ $# -gt 0 ]]; then
    TEST_FILES=("$@")
else
    TEST_FILES=(
        test_discovery.py
        test_automatic_fields.py
        test_all_fields.py
        test_pagination.py
        test_bookmark.py
        test_start_date.py
        test_interrupted_sync.py
    )
fi

# --- run tests ---
cd "${TAP_TESTER_DIR}"
FAILURES=0

for test_file in "${TEST_FILES[@]}"; do
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  Running: ${test_file}"
    echo "════════════════════════════════════════════════════════════"
    if ./bin/run-test --tap=tap-3plcentral "${TAP_DIR}/tests/${test_file}"; then
        echo "✓ ${test_file} PASSED"
    else
        echo "✗ ${test_file} FAILED"
        FAILURES=$((FAILURES + 1))
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════"
if [[ ${FAILURES} -eq 0 ]]; then
    echo "  All tests passed!"
else
    echo "  ${FAILURES} test file(s) failed."
fi
echo "════════════════════════════════════════════════════════════"

exit "${FAILURES}"
