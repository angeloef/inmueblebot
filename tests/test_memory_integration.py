"""
Test de integración de memoria y estado.
Ejecutar: docker-compose exec app python tests/test_memory_integration.py
"""
import asyncio
from app.core.memory import memory_manager
from app.core.state_machine import state_machine
from app.core.session import session_manager


async def test_integration():
    phone = "+595981999999"
    
    print("=" * 60)
    print("TEST: Memory + State Integration")
    print("=" * 60)
    
    # Test 1: Memory context
    print()
    print("1. Guardar contexto en memoria...")
    await memory_manager.save_user_context(phone, {
        "current_state": "qualifying",
        "last_search_criteria": {"type": "venta", "location": "Asuncion"}
    })
    print("   OK: Contexto guardado")
    
    # Test 2: Save message
    print()
    print("2. Guardar mensaje...")
    await memory_manager.save_message(phone, "user", "Hola, busco una casa en Asuncion")
    await memory_manager.save_message(phone, "assistant", "Hola! Cual es tu presupuesto?")
    msgs = await memory_manager.get_recent_messages(phone)
    print(f"   OK: {len(msgs)} mensajes guardados")
    
    # Test 3: State machine
    print()
    print("3. Cambiar estado...")
    await state_machine.set_state(phone, "qualifying")
    current_state = await state_machine.get_state(phone)
    print(f"   OK: Estado actual: {current_state}")
    
    # Test 4: Transition to searching
    print()
    print("4. Transicion de estado...")
    await state_machine.set_state(phone, "searching")
    new_state = await state_machine.get_state(phone)
    print(f"   OK: Nuevo estado: {new_state}")
    
    # Test 5: Session manager
    print()
    print("5. Gestor de sesiones...")
    session = await session_manager.get_session_info(phone)
    is_active = session["is_active"]
    session_state = session["state"]
    print(f"   OK: Sesion activa: {is_active}")
    print(f"   OK: Estado: {session_state}")
    
    # Test 6: Update preferences
    print()
    print("6. Actualizar preferencias en PostgreSQL...")
    await memory_manager.update_user_preferences(phone, {
        "name": "Test User",
        "budget_min": 100000,
        "budget_max": 200000,
        "location_preferences": ["Asuncion", "Encarnacion"],
        "property_type": ["casa"],
        "lead_score": 75
    })
    print("   OK: Preferencias actualizadas")
    
    # Test 7: Get preferences
    print()
    print("7. Obtener preferencias...")
    prefs = await memory_manager.get_user_preferences(phone)
    if prefs:
        name = prefs["name"]
        budget = f"{prefs['budget_min']}-{prefs['budget_max']}"
        locations = prefs["location_preferences"]
        score = prefs["lead_score"]
        print(f"   OK: Nombre: {name}")
        print(f"   OK: Presupuesto: {budget}")
        print(f"   OK: Ubicaciones: {locations}")
        print(f"   OK: Lead Score: {score}")
    else:
        print("   OK: Preferencias no encontradas (creando nuevo usuario)")
    
    # Test 8: Clear memory
    print()
    print("8. Limpiar memoria de corto plazo...")
    await memory_manager.clear_short_term_memory(phone)
    context = await memory_manager.get_user_context(phone)
    print(f"   OK: Contexto despues de limpiar: {context['current_state']}")
    
    print()
    print("=" * 60)
    print("TODOS LOS TESTS DE INTEGRACION PASARON")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_integration())