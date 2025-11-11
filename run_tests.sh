#!/bin/bash
# Test runner for Telegram Shift Tracking Bot

set -e  # Exit on error

echo "======================================================================="
echo "🧪 Running Tests for Telegram Shift Tracking Bot"
echo "======================================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL=0
PASSED=0
FAILED=0

# Function to run a test
run_test() {
    local test_file=$1
    local test_name=$(basename "$test_file" .py)

    TOTAL=$((TOTAL + 1))

    echo "───────────────────────────────────────────────────────────────────────"
    echo "Running: ${test_name}"
    echo "───────────────────────────────────────────────────────────────────────"

    if python3 "$test_file" > /tmp/test_output.log 2>&1; then
        echo -e "${GREEN}✅ PASSED${NC}: ${test_name}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}❌ FAILED${NC}: ${test_name}"
        echo "Last 20 lines of output:"
        tail -20 /tmp/test_output.log
        FAILED=$((FAILED + 1))
    fi
    echo ""
}

# Run integration tests
echo "📦 Integration Tests"
echo "======================================================================="
echo ""

first_test=true
for test_file in tests/integration/test_scenario_*.py; do
    if [ -f "$test_file" ]; then
        # Add delay between tests to avoid Google API quota limits
        if [ "$first_test" = false ]; then
            echo -e "${YELLOW}⏳ Waiting 10 seconds to avoid API quota limits...${NC}"
            sleep 10
        fi
        first_test=false

        run_test "$test_file"
    fi
done

# Summary
echo "======================================================================="
echo "📊 Test Summary"
echo "======================================================================="
echo "Total:  ${TOTAL}"
echo -e "Passed: ${GREEN}${PASSED}${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "Failed: ${RED}${FAILED}${NC}"
else
    echo -e "Failed: ${FAILED}"
fi
echo "======================================================================="

# Exit with error if any tests failed
if [ $FAILED -gt 0 ]; then
    exit 1
fi

exit 0
