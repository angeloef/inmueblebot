"""
Test interactivo de Phase 2.
Ejecutar: docker-compose exec app python -m pytest tests/test_phase2.py -v -s
"""
import pytest
import asyncio
from app.core.memory import memory_manager
from app.core.state_machine import state_machine


@pytest.mark.asyncio
async def test_phase2_memory_and_state():
    """Test completo de memoria y estado."""
    phone = "+595981234567"
    
    print("\n=== Test Phase 2 ===")
    print()
    
    # Save some messages
    print("1. Guardando mensajes...")
    await memory_manager.save_message(phone, "user", "Hola, busco una casa en Posadas")
    await memory_manager.save_message(phone, "assistant", "Claro! Cual es tu presupuesto?")
    await memory_manager.save_message(phone, "user", "Tengo hasta 150000 USD")
    print("   OK: Mensajes guardados")
    
    # Update preferences
    print()
    print("2. Actualizando preferencias...")
    await memory_manager.update_user_preferences(phone, {
        "budget_max": 150000,
        "location_preferences": ["Posadas"],
        "property_type": ["casa"],
        "name": "Test User",
        "lead_score": 60
    })
    print("   OK: Preferencias actualizadas en PostgreSQL")
    
    # Get context
    print()
    print("3. Obteniendo contexto...")
    context = await memory_manager.get_user_context(phone)
    current = context.get("current_state")
    print(f"   Contexto: current_state={current}")
    assert current is not None
    
    # State machine
    print()
    print("4. Maquina de estados...")
    current_state = await state_machine.get_state(phone)
    print(f"   Estado actual: {current_state}")
    
    await state_machine.set_state(phone, "searching")
    new_state = await state_machine.get_state(phone)
    print(f"   Nuevo estado: {new_state}")
    assert new_state == "searching"
    
    # Get messages
    print()
    print("5. Obteniendo mensajes...")
    msgs = await memory_manager.get_recent_messages(phone)
    print(f"   Mensajes: {len(msgs)}")
    assert len(msgs) >= 3
    
    # Get preferences
    print()
    print("6. Obteniendo preferencias...")
    prefs = await memory_manager.get_user_preferences(phone)
    assert prefs is not None
    name = prefs.get("name")
    budget = prefs.get("budget_max")
    locs = prefs.get("location_preferences")
    types = prefs.get("property_type")
    score = prefs.get("lead_score")
    print(f"   Nombre: {name}")
    print(f"   Presupuesto max: {budget}")
    print(f"   Ubicaciones: {locs}")
    print(f"   Tipos: {types}")
    print(f"   Lead Score: {score}")
    assert name == "Test User"
    assert budget == 150000
    assert locs == ["Posadas"]
    assert types == ["casa"]
    assert score == 60
    
    print()
    print("=== TODOS LOS TESTS PASARON ===")


if __name__ == "__main__":
    asyncio.run(test_phase2_memory_and_state())