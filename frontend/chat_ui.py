"""
InmuebleBot - Manual Test Chat Interface
Use Streamlit to test the RealEstateAgent without WhatsApp.

Run from project root:
  streamlit run frontend/chat_ui.py

Or with Docker:
  docker compose up -d streamlit
  # Then open http://localhost:8501
"""
import sys
import os
import requests
import streamlit as st
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Find project root (where app/ folder is)
current_file = Path(__file__).resolve()
project_root = current_file.parent

# Look for app/ folder to confirm we're in right place
if not (project_root / "app").exists():
    for parent in current_file.parents:
        if (parent / "app").exists():
            project_root = parent
            break

sys.path.insert(0, str(project_root))
os.chdir(project_root)

# =============================================================================
# Configuration
# =============================================================================

# API Configuration - uses Docker service name by default
# Override via BACKEND_URL env var or sidebar
# In Docker: http://app:8000 (service name)
# Locally: http://localhost:8000
DEFAULT_API_URL = os.environ.get("BACKEND_URL", "http://app:8000")
API_URL = os.environ.get("API_URL", DEFAULT_API_URL)

# =============================================================================
# Session State Initialization
# =============================================================================

def init_session_state():
    """Initialize session state variables."""
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = {}
    
    if "current_phone" not in st.session_state:
        st.session_state.current_phone = "+595981234567"
    
    if "agent" not in st.session_state:
        from app.agents.real_estate_agent import RealEstateAgent
        st.session_state.agent = RealEstateAgent()
    
    if "api_url" not in st.session_state:
        st.session_state.api_url = API_URL


def get_conversation_history(phone: str) -> list:
    """Get conversation history for a phone."""
    if phone not in st.session_state.conversation_history:
        st.session_state.conversation_history[phone] = []
    return st.session_state.conversation_history[phone]


def add_to_history(phone: str, role: str, content: str):
    """Add message to conversation history."""
    history = get_conversation_history(phone)
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })


def clear_conversation(phone: str):
    """Clear conversation history for a phone."""
    if phone in st.session_state.conversation_history:
        st.session_state.conversation_history[phone] = []


# =============================================================================
# API Connection Test
# =============================================================================

def test_api_connection(url: str) -> tuple[bool, str]:
    """Test connection to the FastAPI backend."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"Error: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)[:50]


def render_connection_indicator():
    """Render connection status in sidebar."""
    api_url = st.session_state.api_url
    
    # Test API connection
    api_ok, api_msg = test_api_connection(api_url)
    
    # Test Redis (via agent)
    redis_ok = False
    try:
        from app.core.memory import memory_manager
        import asyncio
        health = asyncio.run(memory_manager.check_health())
        redis_ok = health.get("status") == "healthy"
    except Exception:
        pass
    
    # Display indicators
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if api_ok:
            st.success("✅ API")
        else:
            st.error("❌ API")
    
    with col2:
        if redis_ok:
            st.success("✅ Redis")
        else:
            st.warning("⚠️ Redis")
    
    # Connection details & retry
    if not api_ok:
        st.sidebar.warning(f"API: {api_msg}")
        st.sidebar.info(f"URL: {api_url}/health")
        
        if st.sidebar.button("🔄 Reintentar conexión"):
            st.rerun()
    
    if not redis_ok:
        st.sidebar.info("Using local memory (limited)")


# =============================================================================
# Sidebar Components
# =============================================================================

def render_sidebar():
    """Render the sidebar with controls."""
    st.sidebar.title("🏠 InmuebleBot")
    st.sidebar.markdown("---")
    
    # Connection Status
    st.sidebar.subheader("🔌 Connection")
    render_connection_indicator()
    
    st.sidebar.markdown("---")
    
    # API URL Configuration
    st.sidebar.subheader("⚙️ Configuration")
    
    api_url_input = st.sidebar.text_input(
        "API Base URL",
        value=st.session_state.api_url,
        help="The FastAPI backend URL"
    )
    
    if api_url_input != st.session_state.api_url:
        st.session_state.api_url = api_url_input
        st.rerun()
    
    # Phone number selector
    st.sidebar.markdown("---")
    st.sidebar.subheader("📱 Teléfono de Prueba")
    
    test_phones = [
        "+595981234567",
        "+59598100001",
        "+59598100002",
        "+59598100003",
        "+59598100010"
    ]
    
    selected_phone = st.sidebar.selectbox(
        "Seleccionar número",
        test_phones,
        index=test_phones.index(st.session_state.current_phone) 
        if st.session_state.current_phone in test_phones else 0
    )
    
    # Custom phone option
    use_custom = st.sidebar.checkbox("Usar número custom")
    if use_custom:
        custom_phone = st.sidebar.text_input("Número personalizado", value=selected_phone)
        selected_phone = custom_phone
    
    # Update current phone if changed
    if selected_phone != st.session_state.current_phone:
        st.session_state.current_phone = selected_phone
        st.rerun()
    
    # Current state display
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Estado Actual")
    
    if st.sidebar.button("🔄 Actualizar Estado"):
        st.rerun()
    
    # Get context asynchronously
    phone = st.session_state.current_phone
    
    # Display info
    with st.sidebar.container():
        st.info(f"**Teléfono:** {phone}")
        
        # Lead score
        lead_score = 0
        preferences = {}
        
        try:
            import asyncio
            from app.core.memory import memory_manager
            context = asyncio.run(memory_manager.get_user_context(phone))
            lead_score = context.get("lead_score", 0)
            preferences = context.get("preferences", {})
        except Exception:
            pass
        
        st.metric("Lead Score", str(lead_score))
        
        # State
        try:
            import asyncio
            from app.core.state_machine import state_machine
            current_state = asyncio.run(state_machine.get_state(phone))
            st.write(f"**Estado:** {current_state}")
        except Exception:
            st.write("**Estado:** unknown")
        
        # Preferences summary
        if preferences:
            st.sidebar.markdown("**Preferencias:**")
            if preferences.get("location_preferences"):
                st.sidebar.write(f"📍 Zona: {preferences['location_preferences']}")
            if preferences.get("budget_max"):
                st.sidebar.write(f"💰 Presupuesto: ${preferences['budget_max']:,}")
            if preferences.get("property_type"):
                st.sidebar.write(f"🏠 Tipo: {preferences['property_type']}")
    
    # LLM Status
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 Estado LLM")
    
    try:
        from app.agents.llm_router import llm_router
        stats = llm_router.get_stats()
        
        gemini_count = stats.get("request_count", {}).get("gemini", 0)
        minimax_count = stats.get("request_count", {}).get("minimax", 0)
        
        if gemini_count > 0:
            st.sidebar.success(f"✅ Gemini: {gemini_count}")
        elif minimax_count > 0:
            st.sidebar.warning(f"⚠️ MiniMax: {minimax_count}")
        else:
            st.sidebar.info("⏳ Sin requests aún")
        
        if st.sidebar.button("🔄 Reset LLM"):
            llm_router.reset_health()
            st.rerun()
            
    except Exception as e:
        st.sidebar.error(f"Error: {e}")
    
    # Actions
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗑️ Acciones")
    
    if st.sidebar.button("🗑️ Limpiar Conversación"):
        clear_conversation(phone)
        st.rerun()
    
    if st.sidebar.button("🔄 Reset Memory"):
        import asyncio
        from app.core.memory import memory_manager
        from app.core.state_machine import state_machine
        asyncio.run(memory_manager.clear_user(phone))
        asyncio.run(state_machine.reset_state(phone))
        clear_conversation(phone)
        st.rerun()
    
    # Links
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔗 Links")
    st.sidebar.markdown(f"[📊 Admin]({API_URL}/admin/leads)")
    st.sidebar.markdown(f"[📖 API Docs]({API_URL}/docs)")
    
    return phone


# =============================================================================
# Property Display
# =============================================================================

def display_properties(properties: list):
    """Display properties in a clean grid layout."""
    if not properties:
        st.info("No se encontraron propiedades.")
        return
    
    # Display up to 6 properties in a grid
    for i in range(0, min(len(properties), 6), 2):
        col1, col2 = st.columns(2)
        
        with col1:
            display_property_card(properties[i])
        
        with col2:
            if i + 1 < len(properties):
                display_property_card(properties[i + 1])
    
    # Show count
    if len(properties) > 6:
        st.info(f"Y {len(properties) - 6} propiedades más...")


def display_property_card(prop: dict):
    """Display a single property as an expander card."""
    title = prop.get("title", "Sin título")
    price = prop.get("price", 0)
    location = prop.get("location", "Sin ubicación")
    bedrooms = prop.get("bedrooms", 0)
    bathrooms = prop.get("bathrooms", 0)
    area = prop.get("area_m2", 0)
    prop_id = prop.get("id", "N/A")
    
    with st.expander(f"🏠 {title[:40]}... | ${price:,}"):
        st.markdown(f"""
        **💰 Precio:** ${price:,}
        
        **📍 Ubicación:** {location}
        
        **🛏️ Habitaciones:** {bedrooms} | **🛁 Baños:** {bathrooms} | **📐 Área:** {area}m²
        
        **🔍 ID:** `{prop_id}`
        """)


# =============================================================================
# Main Chat Interface
# =============================================================================

def render_chat():
    """Render the main chat interface."""
    
    # Header
    st.title("🏠 InmuebleBot - Chat de Pruebas")
    
    # Connection status in main area
    api_url = st.session_state.api_url
    
    with st.spinner("Conectando con el backend..."):
        api_ok, api_msg = test_api_connection(api_url)
    
    if not api_ok:
        st.error(f"⚠️ API no conectada: {api_msg}")
        st.info(f"Backend URL: {api_url}/health")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Reintentar conexión"):
                st.rerun()
        with col2:
            st.info("Asegúrate de que el servicio 'app' esté corriendo en Docker")
    else:
        st.success("✅ Conectado al backend")
    
    # WhatsApp simulation note
    st.info("📱 **Simulando WhatsApp** - Este chat reproduce la experiencia de WhatsApp.")
    
    st.markdown("---")
    
    phone = st.session_state.current_phone
    
    # Display conversation history
    history = get_conversation_history(phone)
    
    if not history:
        # Welcome message
        st.chat_message("assistant").markdown(
            "👋 **¡Hola! Soy InmuebleBot, tu asistente inmobiliario.**\n\n"
            "Estoy aquí para ayudarte a encontrar la propiedad perfecta en Paraguay.\n\n"
            "Puedo ayudarte con:\n"
            "• 🔍 Buscar propiedades en venta o alquiler\n"
            "• 📅 Agendar visitas\n"
            "• 💰 Información sobre presupuestos\n"
            "• 🏠 Detalles de propiedades específicas\n\n"
            "¿Qué estás buscando hoy?"
        )
    
    # Display existing messages
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # Chat input
    if prompt := st.chat_input("Escribe un mensaje...", key=f"chat_{phone}"):
        # Add user message to history
        add_to_history(phone, "user", prompt)
        
        # Display user message
        st.chat_message("user").markdown(prompt)
        
        # Process with agent (with thinking indicator)
        with st.spinner("🤔 Pensando..."):
            try:
                import asyncio
                agent = st.session_state.agent
                
                # Call the agent
                result = asyncio.run(agent.process_turn(phone, prompt))
                
                response_text = result.get("response_text", "Lo siento, no pude procesar tu mensaje.")
                rich_content = result.get("rich_content", {})
                
                # Add bot response to history
                add_to_history(phone, "assistant", response_text)
                
                # Display bot response
                with st.chat_message("assistant"):
                    # STEP 7: Render property images if present
                    if rich_content and rich_content.get("action") == "show_property_images":
                        images = rich_content.get("images", [])
                        if images:
                            cols = st.columns(min(len(images), 3))
                            for i, url in enumerate(images[:3]):
                                with cols[i % 3]:
                                    st.image(url, use_column_width=True)
                            if len(images) > 3:
                                with st.expander(f"Ver todas las fotos ({len(images)})"):
                                    for url in images[3:]:
                                        st.image(url, use_column_width=True)
                    # If details with images, render the primary image above details
                    if rich_content and rich_content.get("action") == "show_property_details":
                        images = rich_content.get("images", [])
                        if images:
                            st.image(images[0], use_column_width=True)
                    st.markdown(response_text)
                    
                    # Display properties if present
                    if rich_content and rich_content.get("properties"):
                        st.markdown("---")
                        st.subheader("🏠 Propiedades Encontradas")
                        display_properties(rich_content["properties"])
                    
                    # Show metadata in expander
                    with st.expander("ℹ️ Metadatos"):
                        st.json(result)
                        
            except Exception as e:
                error_msg = f"❌ Error: {str(e)}"
                add_to_history(phone, "assistant", error_msg)
                st.chat_message("assistant").markdown(error_msg)


# =============================================================================
# Main
# =============================================================================

def main():
    """Main entry point."""
    init_session_state()
    
    phone = render_sidebar()
    render_chat()


if __name__ == "__main__":
    main()
