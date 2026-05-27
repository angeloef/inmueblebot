#!/usr/bin/env python3
"""Run buy_01 through buy_05 against Render API."""
import json, time, sys, os
import urllib.request, urllib.error

API_URL = "https://inmueblebot-api.onrender.com"
API_KEY = "your-secure-admin-key-here"

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

def simulate(phone, message, reset=False):
    payload = json.dumps({"phone": phone, "message": message, "reset": reset}).encode()
    req = urllib.request.Request(
        f"{API_URL}/admin/simulate",
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
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

def check(turn_result, expect, turn_num, verbose=False):
    msgs = []
    passed = True

    if "error" in turn_result:
        msgs.append(fail(f"  Turn {turn_num}: API error: {turn_result['error']} - {turn_result.get('detail','')}"))
        return False, msgs

    resp_text = turn_result.get("response_text", "")
    tools = turn_result.get("tools_used", [])
    state = turn_result.get("next_state", "")
    timing = turn_result.get("timing", {})

    for tool in expect.get("tools_called", []):
        if tool in tools:
            msgs.append(ok(f"  Turn {turn_num}: Tool '{tool}' +"))
        else:
            msgs.append(fail(f"  Turn {turn_num}: Tool '{tool}' MISS (got: {tools})"))
            passed = False

    for phrase in expect.get("response_contains", []):
        if phrase.lower() in resp_text.lower():
            msgs.append(ok(f"  Turn {turn_num}: Contains '{phrase}' +"))
        else:
            msgs.append(fail(f"  Turn {turn_num}: Missing '{phrase}'"))
            passed = False

    for phrase in expect.get("response_not_contains", []):
        if phrase.lower() in resp_text.lower():
            msgs.append(fail(f"  Turn {turn_num}: Forbidden '{phrase}' found"))
            passed = False
        else:
            msgs.append(ok(f"  Turn {turn_num}: No '{phrase}' +"))

    if "state" in expect:
        if state == expect["state"]:
            msgs.append(ok(f"  Turn {turn_num}: State '{state}' +"))
        else:
            msgs.append(fail(f"  Turn {turn_num}: State '{state}' != '{expect['state']}'"))
            passed = False

    if timing:
        total_ms = timing.get("total_ms", timing.get("total", "?"))
        msgs.append(info(f"  Turn {turn_num}: {total_ms}ms"))

    msgs.append(info(f"  Turn {turn_num}: Resp: {resp_text[:120]}..."))
    return passed, msgs


# Load tests
base = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base, "conversation_tests.json")) as f:
    all_tests = json.load(f)["tests"]

buy_tests = [t for t in all_tests if t["id"].startswith("buy_")]

results = {"passed": 0, "failed": 0, "total": len(buy_tests),
           "passed_turns": 0, "total_turns": 0, "details": []}

for test in buy_tests:
    tid = test["id"]
    phone = test["phone"]
    turns = test["turns"]
    name = test["name"]

    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}[{tid}] {name}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    test_passed = True

    for i, turn in enumerate(turns):
        msg = turn["user"]
        expect = turn["expect"]
        reset = (i == 0)

        print(f"\n  User: \"{msg[:100]}\"")
        result = simulate(phone, msg, reset=reset)
        passed, msgs = check(result, expect, i+1)

        for m in msgs:
            print(m)

        results["total_turns"] += 1
        if passed:
            results["passed_turns"] += 1
        else:
            test_passed = False

        time.sleep(0.5)

    if test_passed:
        results["passed"] += 1
        print(f"\n  {ok(f'+ PASS: {tid}')}")
    else:
        results["failed"] += 1
        print(f"\n  {fail(f'x FAIL: {tid}')}")

    results["details"].append({"id": tid, "name": name, "passed": test_passed, "turns": len(turns)})

print(f"\n{BOLD}{'='*60}{RESET}")
print(f"{BOLD}SUMMARY: {results['passed']}/{results['total']} tests passed{RESET}")
print(f"  Turns: {results['passed_turns']}/{results['total_turns']} passed")
for d in results["details"]:
    status = ok("PASS") if d["passed"] else fail("FAIL")
    print(f"  [{status}] {d['id']}")

with open(os.path.join(base, "buy_test_results.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(info("\nResults saved to tests/buy_test_results.json"))
