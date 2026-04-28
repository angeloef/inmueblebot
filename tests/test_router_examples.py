"""
Test interactivo del router con ejemplos en español.
Ejecutar: docker-compose exec app python tests/test_router_examples.py
"""
import asyncio
from app.core.router import router


async def test_examples():
    """Ejecuta ejemplos de prueba del router."""
    
    print("=" * 70)
    print("EJEMPLOS DE PRUEBA DEL ROUTER")
    print("=" * 70)
    
    examples = [
        ("+595981000001", "Hola, busco una casa en Posadas de 2 dormitorios hasta 150000 USD"),
        ("+595981000002", "Quiero agendar una visita"),
        ("+595981000003", "Quiero hablar con un agente humano"),
        ("+595981000004", "Buenas tardes, tengo una pregunta sobre el proceso de compra"),
    ]
    
    for i, (phone, message) in enumerate(examples, 1):
        print()
        print(f"--- Ejemplo {i}: {message[:50]}...")
        print()
        
        try:
            result = await router.process_message(phone, message)
            
            print(f"Intent: {result['intent']}")
            print(f"Next State: {result['next_state']}")
            print(f"Response: {result['response_text']}")
            
            if result.get('rich_content'):
                print(f"Rich Content: {result['rich_content']}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    print()
    print("=" * 70)
    print("PRUEBA COMPLETADA")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_examples())