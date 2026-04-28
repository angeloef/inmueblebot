"""
Script para generar 10 conversaciones de prueba realistas.
Ejecutar: python tests/generate_conversation_tests.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.real_estate_agent import RealEstateAgent
from app.core.memory import memory_manager
from app.core.state_machine import state_machine


SCENARIOS = [
    {
        "id": 1,
        "title": "Simple greeting + property search (budget + location)",
        "phone": "+59598100001",
        "personality": "Pareja joven",
        "messages": [
            "Hola",
            "Busco una casa en Asuncion",
            "Tengo 180 mil de presupuesto",
        ]
    },
    {
        "id": 2,
        "title": "Detailed search with multiple filters",
        "phone": "+59598100002",
        "personality": "Profesional ocupado",
        "messages": [
            "Hola",
            "Departamento en alquiler",
            "2 dormitorios",
        ]
    },
    {
        "id": 3,
        "title": "Property search -> book appointment",
        "phone": "+59598100003",
        "personality": "Primera vez comprador",
        "messages": [
            "Hola me interesa comprar una casa",
            "En Posadas",
            "Quiero agendar una visita",
        ]
    },
    {
        "id": 4,
        "title": "User wants to rent instead of buy",
        "phone": "+59598100004",
        "personality": "Inversionista",
        "messages": [
            "Buenas",
            "Alquilan propiedades",
        ]
    },
    {
        "id": 5,
        "title": "User is a seller",
        "phone": "+59598100005",
        "personality": "Vendedor",
        "messages": [
            "Hola quiero vender mi casa",
        ]
    },
    {
        "id": 6,
        "title": "Appointment reschedule",
        "phone": "+59598100006",
        "personality": "Usuario con cita",
        "messages": [
            "Hola tengo una cita",
            "Quiero cambiar el horario",
        ]
    },
    {
        "id": 7,
        "title": "User asks financing questions (FAQ)",
        "phone": "+59598100007",
        "personality": "Consultante",
        "messages": [
            "Hola tengo una pregunta",
            "Que documentos necesito para comprar",
        ]
    },
    {
        "id": 8,
        "title": "Human handoff request",
        "phone": "+59598100008",
        "personality": "Usuario frustrado",
        "messages": [
            "Hola necesito ayuda",
            "Quiero hablar con un agente humano",
        ]
    },
    {
        "id": 9,
        "title": "Inactive user",
        "phone": "+59598100009",
        "personality": "Usuario inactivo",
        "messages": [
            "Buenas",
            "Tengo una casa en venta",
        ]
    },
    {
        "id": 10,
        "title": "Mixed language",
        "phone": "+59598100010",
        "personality": "Usuario bilingue",
        "messages": [
            "Hi looking for property",
            "Casa en Asuncion",
        ]
    },
]


async def run_conversation(agent: RealEstateAgent, scenario: dict) -> dict:
    """Ejecuta una conversación completa para un escenario."""
    phone = scenario["phone"]
    messages = scenario["messages"]
    
    conversation_log = []
    tools_used_all = []
    
    for user_msg in messages:
        try:
            result = await agent.process_turn(phone, user_msg)
            
            bot_response = result.get("response_text", "")
            if len(bot_response) > 300:
                bot_response = bot_response[:300] + "..."
            
            conversation_log.append({
                "user": user_msg,
                "bot": bot_response,
                "state": result.get("next_state", ""),
                "tools": result.get("tools_used", [])
            })
            
            tools_used_all.extend(result.get("tools_used", []))
            
        except Exception as e:
            conversation_log.append({
                "user": user_msg,
                "bot": f"[ERROR: {str(e)}]",
                "state": "error",
                "tools": []
            })
    
    try:
        final_context = await memory_manager.get_user_context(phone)
        final_state = await state_machine.get_state(phone)
        lead_score = final_context.get("lead_score", 0)
        preferences = final_context.get("preferences", {})
    except Exception:
        final_state = "unknown"
        lead_score = 0
        preferences = {}
    
    return {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "phone": phone,
        "personality": scenario["personality"],
        "messages": messages,
        "conversation_log": conversation_log,
        "final_state": final_state,
        "lead_score": lead_score,
        "preferences": preferences,
        "tools_used": list(set(tools_used_all))
    }


def format_conversation(result: dict) -> str:
    """Formatea una conversación para el archivo de salida."""
    lines = []
    
    lines.append("=" * 50)
    lines.append(f"CONVERSATION #{result['scenario_id']} - SCENARIO: {result['title']}")
    lines.append(f"Phone: {result['phone']}")
    lines.append(f"Personality: {result['personality']}")
    lines.append(f"Final Lead Score: {result['lead_score']}")
    lines.append(f"Final State: {result['final_state']}")
    lines.append("=" * 50)
    lines.append("")
    
    for turn in result["conversation_log"]:
        user_msg = turn["user"]
        bot_msg = turn["bot"]
        
        lines.append(f"[User]: {user_msg}")
        lines.append("")
        lines.append(f"[Bot]: {bot_msg[:500]}{'...' if len(bot_msg) > 500 else ''}")
        lines.append("")
    
    summary_parts = []
    if result["preferences"].get("location_preferences"):
        summary_parts.append(f"Ubicación: {result['preferences']['location_preferences']}")
    if result["preferences"].get("budget_max"):
        summary_parts.append(f"Presupuesto: ${result['preferences']['budget_max']:,}")
    if result["preferences"].get("property_type"):
        summary_parts.append(f"Tipo: {result['preferences']['property_type']}")
    
    summary = ", ".join(summary_parts) if summary_parts else "Sin preferencias guardadas"
    lines.append(f"Summary: {summary}")
    lines.append("")
    lines.append(f"Tools Used: {', '.join(result['tools_used']) if result['tools_used'] else 'None'}")
    lines.append("")
    
    return "\n".join(lines)


async def main():
    """Función principal que ejecuta todas las conversaciones."""
    print("Starting conversation generation...")
    print("=" * 50)
    
    agent = RealEstateAgent()
    results = []
    
    for scenario in SCENARIOS:
        print(f"\nScenario #{scenario['id']}: {scenario['title']}")
        print(f"   Phone: {scenario['phone']}")
        
        try:
            result = await run_conversation(agent, scenario)
            results.append(result)
            print(f"   Completed - State: {result['final_state']}, Score: {result['lead_score']}")
        except Exception as e:
            print(f"   Failed: {str(e)}")
            results.append({
                "scenario_id": scenario["id"],
                "title": scenario["title"],
                "phone": scenario["phone"],
                "error": str(e)
            })
        
        await asyncio.sleep(1)
    
    timestamp = datetime.now().strftime("%Y%m%d")
    output_file = Path(__file__).parent / f"test_conversations_{timestamp}.txt"
    
    print(f"\nAttempting to write to: {output_file}")
    
    file_created = False
    try:
        with open(output_file, "w", encoding="utf-8", errors="replace") as f:
            f.write("INMUEBLEBOT CONVERSATION TESTS\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Scenarios: {len(SCENARIOS)}\n")
            f.write("=" * 50)
            f.write("\n\n")
            
            for result in results:
                if "error" in result:
                    f.write(f"SCENARIO #{result['scenario_id']}: FAILED - {result['error']}\n\n")
                else:
                    try:
                        f.write(format_conversation(result))
                    except Exception as conv_err:
                        f.write(f"SCENARIO #{result['scenario_id']}: Error formatting: {conv_err}\n")
                    f.write("\n")
            
            f.flush()
        
        file_created = True
        print(f"File written successfully!")
    except Exception as e:
        print(f"Error writing file: {e}")
        import traceback
        traceback.print_exc()
        file_created = False
    
    print("\n" + "=" * 50)
    if file_created:
        print(f"10 conversations generated and saved to {output_file.name}")
    else:
        print(f"Conversations generated but file write failed")
    print("=" * 50)
    
    successful = len([r for r in results if "error" not in r])
    print(f"\nResults: {successful}/{len(SCENARIOS)} successful")
    
    return results


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")