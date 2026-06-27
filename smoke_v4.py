"""Quick smoke test for v4 adapter — run with: python smoke_v4.py"""
import asyncio
import os

with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


async def smoke() -> None:
    from app.routers.v4.adapter import process_turn_v4

    tests = [
        ("Hola, busco departamento en alquiler en el centro de Oberá", "saludo+busqueda"),
        ("tienen departamentos de 3 dormitorios disponibles?", "busqueda-dorm"),
        ("que requisitos piden para alquilar?", "faq-requisitos"),
        ("quiero coordinar una visita", "scheduling"),
        ("gracias por la info!", "smalltalk"),
    ]
    phone = "smoke-v4-001"
    print("=" * 60)
    print("SMOKE TEST V4")
    print("=" * 60)
    for msg, label in tests:
        try:
            r = await process_turn_v4(phone=phone, user_message=msg, bsuid=None, tenant=None)
            resp = r.get("response_text", "") or ""
            rl = r.get("router_label", "?")
            conf = r.get("confidence", 0)
            ec = (r.get("rich_content") or {}).get("evidence_coverage") or {}
            abstain = ec.get("should_abstain", False)
            sub_goals = (r.get("rich_content") or {}).get("sub_goals", [])
            print(f"\n[{label}]")
            print(f"  router={rl}  conf={conf:.2f}  abstain={abstain}  sub_goals={len(sub_goals)}")
            print(f"  resp: {resp[:180]}")
            status = "OK" if "error" not in rl else "FAIL"
            print(f"  -> {status}")
        except Exception as e:
            print(f"\n[{label}] EXCEPTION: {e}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(smoke())
