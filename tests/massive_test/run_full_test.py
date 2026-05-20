#! /usr/bin/env python3
"""
run_full_test.py — Enhanced Monte Carlo Test v3.

Changes from v2:
- 12 profiles instead of 8 (added lead capture, handoff, preferences, reschedule/cancel)
- 29 known edges instead of 19
- 16 validation rules instead of 10
- ~30% erratic behavior per turn (wrong IDs, confusion, intent changes, contradictions, typos)
- Per-profile session counts for better weight distribution
- New stats: tools not covered, per-rule violations, Spanish language check
"""
import sys
import time
import random
import httpx

sys.stdout.reconfigure(line_buffering=True)

from profiles import PROFILES
from validators import validate_all
from coverage_tracker import CoverageTracker, KNOWN_EDGES
from orchestrator import (
    run_session, check_health, simulate_turn, infer_state_from_response,
    SIMULATE_URL, HEADERS, BASE_URL,
    TURN_DELAY, SESSION_DELAY, KEEPALIVE_INTERVAL,
    PER_PROFILE_SESSIONS, TOTAL_SESSIONS, MAX_TURNS,
)


def main():
    # Use a fixed seed for reproducibility
    TEST_SEED = int(time.time())
    random.seed(TEST_SEED)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   InmuebleBot — MASS TEST v3                               ║")
    print("║   12 perfiles · 16 reglas · 29 edges                       ║")
    print("║   Todos los tools + lead/handoff/preferences               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"Target:       {SIMULATE_URL}")
    print(f"Profiles:     {len(PROFILES)}")
    print(f"Sessions:     {TOTAL_SESSIONS}")
    print(f"Known edges:  {len(KNOWN_EDGES)}")
    print(f"Seed:         {TEST_SEED}")
    print(f"Start time:   {time.strftime('%H:%M:%S')}")
    print(f"Delay/turn:   {TURN_DELAY}s   Delay/session:  {SESSION_DELAY}s")
    print()

    with httpx.Client() as client:
        if not check_health(client):
            print("🔴 API unreachable. Aborting.")
            sys.exit(1)
        print("🟢 API healthy")
        print()

        tracker = CoverageTracker()
        all_session_data = []
        start_wall = time.time()
        last_keepalive = time.time()
        session_idx = 0

        # ── Calibration ──
        print("=" * 64)
        print("📌 CALIBRATION (2 warm-up sessions)")
        print("=" * 64)
        for i in range(2):
            profile = PROFILES[i % len(PROFILES)]
            sess = run_session(client, profile, 9990 + i, tracker)
            turns = len(sess.get("turns", []))
            print(f"  [{i + 1}/2] {profile['name']:35s} → {'✅' if turns > 0 else '❌'} {turns}t")
            all_session_data.append(sess)
            time.sleep(SESSION_DELAY)
        print()

        # ── Main Execution ──
        print("=" * 64)
        print(f"📌 MAIN EXECUTION ({TOTAL_SESSIONS} sessions)")
        print("=" * 64)
        session_idx = 2  # after calibration

        for pi, profile in enumerate(PROFILES):
            sess_count = PER_PROFILE_SESSIONS.get(pi, 4)
            for si in range(sess_count):
                if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                    check_health(client)
                    last_keepalive = time.time()

                progress_pct = (session_idx / (TOTAL_SESSIONS + 2)) * 100
                print(f"\n[{session_idx}/{TOTAL_SESSIONS + 2} | {progress_pct:.0f}%] "
                      f"📋 {profile['name']} (s{si + 1}/{sess_count})")

                sess = run_session(client, profile, TEST_SEED + session_idx, tracker)
                turns = len(sess.get("turns", []))
                tools_used = set()
                turn_details = []
                for t in sess.get("turns", []):
                    tools_used.update(t.get("tools_used", []))
                    turn_details.append((t["turn"], t["tools_used"], t["inferred_state"]))

                viol_count = sum(1 for t in sess.get("turns", [])
                                 for v in t.get("validations", []))

                status_mark = "✅" if turns > 0 else "⚠️"
                state_seq = " → ".join([d[2] for d in turn_details])
                print(f"  {status_mark} {turns}t | tools={list(tools_used)[:5]} | "
                      f"states={state_seq[:70]} | viol={viol_count}")

                all_session_data.append(sess)
                session_idx += 1

                if session_idx <= TOTAL_SESSIONS + 2:
                    time.sleep(SESSION_DELAY)

        # ── Final Report ──
        elapsed_m = (time.time() - start_wall) / 60
        print()
        print("=" * 64)
        print("📊 FINAL REPORT v3")
        print("=" * 64)
        print()
        print(tracker.report())
        print()

        # Per-profile breakdown
        print("  Per-Profile Results:")
        h = f"  {'Profile':40s} {'Sess':>4s} {'Turns':>5s} {'Avg':>5s} {'Viol':>4s}"
        print(h)
        print(f"  {'-'*40} {'-'*4} {'-'*5} {'-'*5} {'-'*4}")
        total_viol = 0
        for profile in PROFILES:
            pname = profile["name"]
            p_sessions = [r for r in all_session_data if r.get("profile") == pname]
            total_t = sum(len(s.get("turns", [])) for s in p_sessions)
            avg_t = total_t / max(len(p_sessions), 1)
            p_viol = sum(1 for s in p_sessions for t in s.get("turns", [])
                         for v in t.get("validations", []))
            total_viol += p_viol
            print(f"  {pname:40s} {len(p_sessions):>4d} {total_t:>5d} {avg_t:>4.1f}  {p_viol:>4d}")
        print()

        # Tool coverage
        ALL_KNOWN_TOOLS = [
            "search_properties", "refine_search", "get_property_details",
            "recommend_properties", "update_user_preferences", "get_user_preferences",
            "save_lead_info", "schedule_visit", "reschedule_appointment",
            "cancel_appointment", "get_my_appointments",
            "request_human_assistance", "get_property_images",
            "get_faq_answer", "compare_properties",
        ]
        all_tools = set()
        for s in all_session_data:
            for t in s.get("turns", []):
                all_tools.update(t.get("tools_used", []))
        covered = [t for t in ALL_KNOWN_TOOLS if t in all_tools]
        missing = [t for t in ALL_KNOWN_TOOLS if t not in all_tools]
        print(f"  Tools detected ({len(all_tools)}/{len(ALL_KNOWN_TOOLS)}):")
        print(f"    Covered: {', '.join(sorted(covered))}")
        if missing:
            print(f"    ❌ MISSING: {', '.join(missing)}")
        else:
            print(f"    ✅ ALL TOOLS COVERED")
        print()

        # Timing
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
            print(f"  Timing ({len(all_times)} turns):")
            print(f"    Avg: {avg_t:.2f}s | Min: {min_t:.2f}s | Max: {max_t:.2f}s | "
                  f"Wall: {elapsed_m:.1f}min")

        # Violations breakdown
        if tracker.violations:
            print()
            print("  Violations by Rule:")
            rule_counts = {}
            for _, _, rule, _ in tracker.violations:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
            for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
                print(f"    {rule:35s} × {count}")

            # Show FAIL vs WARN breakdown
            fail_count = sum(1 for _, _, rule, _ in tracker.violations if rule != "TIMING" and rule != "LANGUAGE" and rule != "NOT-STALE-CONTEXT")
            warn_count = sum(1 for _, _, rule, _ in tracker.violations if rule in ["TIMING", "LANGUAGE", "NOT-STALE-CONTEXT"])
            print(f"    ─────────────────────────────────────")
            print(f"    {'FAIL violations:':35s} × {fail_count}")
            print(f"    {'WARN violations:':35s} × {warn_count}")

            print()
            print("  Last 20 violations:")
            for sid, turn, rule, msg in tracker.violations[-20:]:
                print(f"    s={sid} t={turn} | {rule}: {msg[:120]}")
        else:
            print()
            print("  🏆 ZERO VIOLATIONS across all sessions!")

        # Summary
        print()
        print("=" * 64)
        print(f"📌 COMPLETE at {time.strftime('%H:%M:%S')}")
        print(f"   Wall time:   {elapsed_m:.1f} min")
        print(f"   Sessions:    {tracker.sessions}")
        print(f"   Turns:       {tracker.total_turns}")
        print(f"   Edges:       {tracker.edge_coverage:.1f}% ({len(tracker.edges_visited)}/{len(KNOWN_EDGES)})")
        print(f"   Tools:       {len(all_tools)}/{len(ALL_KNOWN_TOOLS)}")
        print(f"   Violations:  {len(tracker.violations)}")
        print("=" * 64)


if __name__ == "__main__":
    main()
