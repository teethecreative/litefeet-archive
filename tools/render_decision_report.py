import json
from pathlib import Path

REPORT_PATH = Path("performance_audit_report.json")


def main():
    if not REPORT_PATH.exists():
        print("No performance_audit_report.json found. Run tools/performance_audit.py first.")
        raise SystemExit(1)

    data = json.loads(REPORT_PATH.read_text())
    results = data.get("results", [])

    errors = [item for item in results if item.get("status", 0) >= 500]
    slow = [item for item in results if (item.get("median_ms") or 0) >= 1500]
    medium = [item for item in results if 800 <= (item.get("median_ms") or 0) < 1500]
    heavy = [item for item in results if (item.get("avg_size_bytes") or 0) >= 750000]

    print("=== Render / Performance Decision Report ===")
    print(f"database: {data.get('database')}")
    print(f"generated_at: {data.get('generated_at')}")
    print("")

    if errors:
        print("Decision: FIX CODE FIRST")
        print("Reason: at least one route returned a 500-level error.")
        for item in errors:
            print(f"- {item['path']} status={item['status']}")
        return

    if slow:
        print("Decision: ROUTE OPTIMIZATION FIRST")
        print("Reason: at least one route is slow locally before Render is involved.")
        for item in slow:
            print(f"- {item['path']} median={item['median_ms']}ms max={item['max_ms']}ms")
        print("")
        print("Next step: optimize the listed route templates/queries before upgrading Render.")
        return

    if heavy:
        print("Decision: PAGE WEIGHT CLEANUP")
        print("Reason: at least one route is sending a large response body.")
        for item in heavy:
            print(f"- {item['path']} avg_size={int(item['avg_size_bytes'])} bytes")
        print("")
        print("Next step: trim heavy template output, large lists, embeds, or images before upgrading Render.")
        return

    if medium:
        print("Decision: WATCH + TARGETED CLEANUP")
        print("Reason: routes are not failing, but some are close to slow.")
        for item in medium:
            print(f"- {item['path']} median={item['median_ms']}ms")
        print("")
        print("Next step: target these routes, then compare live Render speed.")
        return

    print("Decision: LOCAL CODE LOOKS OK")
    print("Reason: no 500s and no local route median crossed 800ms.")
    print("")
    print("If the live site still feels slow, the likely causes are Render cold starts, free/low-tier instance limits, database latency, or external assets.")
    print("Next step: compare this local report against live browser load times. If live is much slower than local, upgrading Render is reasonable.")


if __name__ == "__main__":
    main()
