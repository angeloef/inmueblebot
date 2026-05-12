#! /usr/bin/env python3
"""Wrapper that runs the orchestrator with unbuffered output and saves results."""
import sys
sys.stdout.reconfigure(line_buffering=True)

from profiles import PROFILES
from validators import validate_all
from coverage_tracker import CoverageTracker, KNOWN_EDGES
from orchestrator import (
    run_session, check_health, simulate_turn, infer_state_from_response,
    SIMULATE_URL, HEADERS, BASE_URL,
    TURN_DELAY, SESSION_DELAY, KEEPALIVE_INTERVAL,
    SESSIONS_PER_PROFILE, MAX_TURNS,
)
import httpx
import time
import json

def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   InmuebleBot — Monte Carlo Mass Test Suite               ║")
    print("║   Markov Chain Coverage + 10 Validation Rules             ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Target: {SIMULATE_URL}")
    print(f"Profiles: {len(PROFILES)}")
    print(f"Sessions per profile: {SESSIONS_PER_PROFILE}")
    print(f"Total sessions: {len(PROFILES) * SESSIONS_PER_PROFILE}")
    print(f"Start time: {time.strftime('%H:%M:%S')}")
    print()

    with httpx.Client() as client:
        if not check_health(client):
            print("🔴 API unreachable. Aborting.")
            sys.exit(1)
        print("🟢 API healthy")
        print()

        tracker = CoverageTracker()
        all_session_data = []
        last_keepalive = time.time()
        session_idx = 0
        total_planned = len(PROFILES) * SESSIONS_PER_PROFILE

        for pi, profile in enumerate(PROFILES):
            for si in range(SESSIONS_PER_PROFILE):
                # Keepalive
                if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                    check_health(client)
                    last_keepalive = time.time()

                progress_pct = (session_idx / total_planned) * 100
                print(f"[{session_idx + 1}/{total_planned} | {progress_pct:.0f}%] "
                      f"📋 {profile['name']} (s{si + 1})")

                sess = run_session(client, profile, session_idx + 1000, tracker)
                turns = len(sess.get("turns", []))
                tools_used = set()
                for t in sess.get("turns", []):
                    tools_used.update(t.get("tools_used", []))

                status_mark = "✅" if turns > 0 else "⚠️"
                viol_count = sum(1 for t in sess.get("turns", [])
                                 for v in t.get("validations", []))
                print(f"  {status_mark} {turns} turns | "
                      f"tools={list(tools_used)[:5]} | violations={viol_count}")

                all_session_data.append(sess)
                session_idx += 1

                if session_idx < total_planned:
                    time.sleep(SESSION_DELAY)

        # ── Final Report ──
        print()
        print("=" * 64)
        print("📊 FINAL REPORT")
        print("=" * 64)
        print()

        # Coverage
        print(tracker.report())
        print()

        # Per-profile
        print("  Per-Profile Results:")
        header = f"  {'Profile':30s} {'Sess':>4s} {'Turns':>5s} {'Avg':>5s} {'Fail':>5s}"
        print(header)
        print(f"  {'-'*30} {'-'*4} {'-'*5} {'-'*5} {'-'*5}")
        for profile in PROFILES:
            pname = profile["name"]
            p_sessions = [r for r in all_session_data if r.get("profile") == pname]
            total_t = sum(len(s.get("turns", [])) for s in p_sessions)
            avg_t = total_t / max(len(p_sessions), 1)
            p_viol = sum(1 for s in p_sessions for t in s.get("turns", [])
                         for v in t.get("validations", []))
            print(f"  {pname:30s} {len(p_sessions):>4d} {total_t:>5d} {avg_t:>4.1f}  {p_viol:>4d}")
        print()

        # Violations
        if tracker.violations:
            print("  Violations by Rule:")
            rule_counts = {}
            for _, _, rule, _ in tracker.violations:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
            for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
                print(f"    {rule:25s} × {count}")

            print()
            print("  Last 15 violations (for debugging):")
            for sid, turn, rule, msg in tracker.violations[-15:]:
                print(f"    s={sid} t={turn} | {rule}: {msg[:120]}")
        else:
            print("  ✅ ZERO VIOLATIONS across all sessions!")
        print()

        # Tools detected across all sessions
        all_tools = set()
        for s in all_session_data:
            for t in s.get("turns", []):
                all_tools.update(t.get("tools_used", []))
        print(f"  Tools detected: {sorted(all_tools)}")
        print()

        # Timing stats
        all_times = []
        for s in all_session_data:
            for t in s.get("turns", []):
                tt = t.get("timing", {}).get("turn_seconds", 0)
                if tt > 0:
                    all_times.append(tt)
        if all_times:
            avg_t = sum(all_times) / len(all_times)
            max_t = max(all_times)
            min_t = min(all_times)
            print(f"  Timing stats ({len(all_times)} turns):")
            print(f"    Avg: {avg_t:.2f}s | Min: {min_t:.2f}s | Max: {max_t:.2f}s")
        print()

        print("=" * 64)
        print(f"📌 COMPLETE at {time.strftime('%H:%M:%S')}")
        print(f"   Sessions: {tracker.sessions}")
        print(f"   Turns:    {tracker.total_turns}")
        print(f"   Coverage: {tracker.edge_coverage:.1f}% ({len(tracker.edges_visited)}/{len(KNOWN_EDGES)} edges)")
        print(f"   Violations: {len(tracker.violations)}")
        print("=" * 64)

if __name__ == "__main__":
    main()
