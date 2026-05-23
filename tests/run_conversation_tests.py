#!/usr/bin/env python3
"""
InmuebleBot Conversation Test Runner

Runs all 20 conversation tests from conversation_tests.json
against the deployed Render API via POST /admin/simulate.

Usage:
  python3 tests/run_conversation_tests.py                          # all tests
  python3 tests/run_conversation_tests.py --test rent_01           # single test
  python3 tests/run_conversation_tests.py --rent                   # rent only
  python3 tests/run_conversation_tests.py --buy                    # buy only
  python3 tests/run_conversation_tests.py --verbose                # show full responses
  python3 tests/run_conversation_tests.py --output results.json    # save results

Env vars:
  INMUEBLEBOT_API_URL    default: https://inmueblebot-api.onrender.com
  ADMIN_API_KEY          required
"""
import json, sys, time, os, argparse
import urllib.request
import urllib.error
from pathlib import Path

API_URL = os.getenv("INMUEBLEBOT_API_URL", "https://inmueblebot-api.onrender.com")
API_KEY = os.getenv("ADMIN_API_KEY", "")

# ── Color helpers ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def ok(s):   return f"{GREEN}{s}{RESET}"
def fail(s): return f"{RED}{s}{RESET}"
def warn(s): return f"{YELLOW}{s}{RESET}"
def info(s): return f"{CYAN}{s}{RESET}"


def simulate_turn(phone: str, message: str, reset: bool = False) -> dict:
    """Call POST /admin/simulate and return the parsed response."""
    payload = json.dumps({"phone": phone, "message": message, "reset": reset}).encode()
    req = urllib.request.Request(
        f"{API_URL}/admin/simulate",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500] if e.fp else ""
        return {"error": f"HTTP {e.code}", "detail": body}
    except Exception as e:
        return {"error": str(e)}


def check_expectations(turn_result: dict, expect: dict, turn_num: int, verbose: bool) -> tuple[bool, list[str]]:
    """Validate turn result against expectations. Returns (passed, messages)."""
    msgs = []
    passed = True

    if "error" in turn_result:
        msgs.append(fail(f"  ✗ API error: {turn_result['error']} - {turn_result.get('detail','')}"))
        return False, msgs

    response_text = turn_result.get("response_text", "")
    tools_used = turn_result.get("tools_used", [])
    state = turn_result.get("next_state", "")
    timing = turn_result.get("timing", {})

    # Check tools
    expected_tools = expect.get("tools_called", [])
    if expected_tools:
        for tool in expected_tools:
            if tool in tools_used:
                msgs.append(ok(f"  ✓ Tool called: {tool}"))
            else:
                msgs.append(fail(f"  ✗ Tool NOT called: {tool} (got: {tools_used})"))
                passed = False
    else:
        if not tools_used:
            msgs.append(ok(f"  ✓ No tools called (as expected)"))
        else:
            msgs.append(warn(f"  ⚠ Tools called unexpectedly: {tools_used}"))

    # Check response contains
    for phrase in expect.get("response_contains", []):
        if phrase.lower() in response_text.lower():
            msgs.append(ok(f"  ✓ Response contains: '{phrase}'"))
        else:
            msgs.append(fail(f"  ✗ Response missing: '{phrase}'"))
            passed = False

    # Check response NOT contains
    for phrase in expect.get("response_not_contains", []):
        if phrase.lower() in response_text.lower():
            msgs.append(fail(f"  ✗ Response contains forbidden: '{phrase}'"))
            passed = False
        else:
            msgs.append(ok(f"  ✓ Response does NOT contain: '{phrase}'"))

    # Check state
    expected_state = expect.get("state")
    if expected_state:
        if state == expected_state:
            msgs.append(ok(f"  ✓ State: {state}"))
        else:
            msgs.append(fail(f"  ✗ State: got '{state}', expected '{expected_state}'"))
            passed = False

    # Timing info
    if timing:
        total_ms = timing.get("total_ms", timing.get("total", "?"))
        msgs.append(info(f"  ⏱ {total_ms}ms"))

    if verbose:
        msgs.append(info(f"  Response: {response_text[:200]}..."))

    return passed, msgs


def run_tests(tests: list, verbose: bool = False) -> dict:
    """Run all test conversations. Returns results dict."""
    results = {"passed": 0, "failed": 0, "total_tests": len(tests),
               "total_turns": 0, "passed_turns": 0, "details": []}

    for test in tests:
        tid = test["id"]
        phone = test["phone"]
        turns = test["turns"]
        name = test["name"]
        op = test["operation"]

        print(f"\n{BOLD}{'─'*70}{RESET}")
        print(f"{BOLD}[{tid}] {name} ({op}) — {len(turns)} turns{RESET}")
        print(f"{BOLD}{'─'*70}{RESET}")

        test_passed = True

        for i, turn in enumerate(turns):
            user_msg = turn["user"]
            expect = turn.get("expect", {})
            reset = (i == 0)  # reset context on first turn of each test

            print(f"\n  Turn {i+1}/{len(turns)}: \"{user_msg[:80]}...\" " if len(user_msg) > 80 else f"\n  Turn {i+1}/{len(turns)}: \"{user_msg}\"")

            turn_result = simulate_turn(phone, user_msg, reset=reset)
            passed, msgs = check_expectations(turn_result, expect, i+1, verbose)

            for m in msgs:
                print(m)

            results["total_turns"] += 1
            if passed:
                results["passed_turns"] += 1
            else:
                test_passed = False

            # Small delay between turns
            time.sleep(0.5)

        if test_passed:
            results["passed"] += 1
            print(f"\n  {ok(f'✓ TEST PASSED: {tid}')}")
        else:
            results["failed"] += 1
            print(f"\n  {fail(f'✗ TEST FAILED: {tid}')}")

        results["details"].append({
            "id": tid,
            "name": name,
            "passed": test_passed,
            "turns": len(turns),
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="InmuebleBot Conversation Test Runner")
    parser.add_argument("--test", help="Run a specific test by ID (e.g. rent_01_basic_search)")
    parser.add_argument("--rent", action="store_true", help="Run rent tests only")
    parser.add_argument("--buy", action="store_true", help="Run buy tests only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full bot responses")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    args = parser.parse_args()

    # Load tests
    tests_path = Path(__file__).parent / "conversation_tests.json"
    if not tests_path.exists():
        print(fail(f"Test file not found: {tests_path}"))
        sys.exit(1)

    data = json.loads(tests_path.read_text())
    all_tests = data["tests"]

    # Filter
    if args.test:
        all_tests = [t for t in all_tests if t["id"] == args.test]
        if not all_tests:
            print(fail(f"Test '{args.test}' not found"))
            sys.exit(1)
    elif args.rent:
        all_tests = [t for t in all_tests if t["operation"] == "rent"]
    elif args.buy:
        all_tests = [t for t in all_tests if t["operation"] == "buy"]

    if not API_KEY or API_KEY == "":
        print(fail("ADMIN_API_KEY not set. Export it or pass via environment."))
        sys.exit(1)

    print(f"{BOLD}InmuebleBot Conversation Test Runner{RESET}")
    print(f"API: {API_URL}")
    print(f"Tests to run: {len(all_tests)}")
    print(f"API key: {'✓ set' if API_KEY else '✗ missing'}")

    results = run_tests(all_tests, verbose=args.verbose)

    # Summary
    print(f"\n{BOLD}{'═'*70}{RESET}")
    print(f"{BOLD}RESULTS: {results['passed']}/{results['total_tests']} tests passed{RESET}")
    print(f"  Turns: {results['passed_turns']}/{results['total_turns']} passed")
    if results["failed"] > 0:
        print(fail(f"  {results['failed']} tests FAILED"))
        for d in results["details"]:
            if not d["passed"]:
                print(fail(f"    ✗ {d['id']}: {d['name']}"))
    else:
        print(ok("  All tests passed! 🎉"))

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
