import asyncio
from app.core.router import Router

async def test():
    phone = "+595981234567"
    router = Router()
    
    queries = [
        "Hola",
        "Busco casas en Posadas hasta 150000",
        "Quiero agendar una visita para la primera propiedad"
    ]
    
    for q in queries:
        result = await router.process_message(phone, q)
        print(f"\nQuery: {q}")
        response = result.get("response_text", "")[:250]
        print(f"Response: {response}...")

asyncio.run(test())