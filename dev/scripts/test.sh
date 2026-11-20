#!/usr/bin/env bash
# Run the gic_erp test suite on the dedicated test site (never on the dev site:
# the Frappe test runner commits data as it goes).
# Usage: dev/scripts/test.sh                                   all tests
#        dev/scripts/test.sh --module gic_erp.tests.test_foundry
set -euo pipefail
# shellcheck source=dev/scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_docker
site="${GIC_TEST_SITE:-gic-test.local}"
in_bench "bench --site $site migrate >/dev/null && bench --site $site run-tests --app gic_erp $*"
