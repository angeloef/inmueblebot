# How MiniMax M2.5 Tool Calling Works in This Setup

## Overview

This document explains how the MiniMax M2.5 model is integrated with tool calling capabilities in InmuebleBot.

## Architecture

```
User Message → Router → Fast Path (simple intents)
                    → Agent Path (complex intents) → MiniMax M2.5
                                                    ↓
                                            Tool Calling Loop
                                                    ↓
                                            Execute Tools
                                                    ↓
                                            Return Response
```

## Tool Calling Flow

### 1. Request Format (OpenAI-compatible)

MiniMax M2.5 via OpenRouter supports the OpenAI function calling format:

```json
{
  "model": "minimax/m2.2-free",
  "messages": [
    {"role": "system", "content": "Eres InmuebleBot..."},
    {"role": "user", "content": "Busco casa en Asunción"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_properties",
        "description": "Busca propiedades según criterios...",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "Ciudad o zona..."},
            "budget_max": {"type": "number", "description": "Presupuesto máximo..."}
          }
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

### 2. Response Format

The LLM returns either:
- **Regular response**: `{"content": "Hola, ¿en qué puedo ayudarte?", "finish_reason": "stop"}`
- **Tool call request**: 
```json
{
  "content": null,
  "tool_calls": [
    {
      "function": {
        "name": "search_properties",
        "arguments": "{\"location\": \"Asunción\", \"budget_max\": 100000}"
      }
    }
  ],
  "finish_reason": "tool_calls"
}
```

### 3. Tool Execution Loop

The agent executes tools in a loop:

```
1. Send message to LLM
2. If no tool_calls → return response
3. For each tool_call:
   a. Parse tool name and arguments
   b. Execute tool function
   c. Append tool result to messages
4. Send messages + tool results to LLM
5. Repeat until no more tool calls (max 5 iterations)
```

## Key Components

### app/agents/llm.py - AsyncMiniMaxClient

```python
class AsyncMiniMaxClient:
    async def ainvoke(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.7
    ) -> LLMResponse:
        # Makes API call to OpenRouter with tool definitions
        # Returns LLMResponse with content and/or tool_calls

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_handler: Callable,
        max_tool_calls: int = 5
    ) -> str:
        # Automatic tool execution loop
        # Useful for simpler use cases
```

### app/agents/tools.py

Defines async functions that can be called by the LLM:

- `search_properties(criteria)` - Search properties in DB
- `get_property_details(property_id)` - Get property details
- `recommend_properties(user_preferences)` - AI recommendations
- `update_user_preferences(phone, ...)` - Save user preferences
- `get_user_preferences(phone)` - Get saved preferences
- `save_lead_info(phone, ...)` - Save lead information

### app/agents/real_estate_agent.py

Main orchestration:

```python
class RealEstateAgent:
    async def process_turn(
        self,
        phone: str,
        user_message: str,
        intent: Intent = None
    ) -> dict:
        # 1. Load context from memory
        # 2. Build messages for LLM
        # 3. Execute tool calling loop
        # 4. Save response to memory
        # 5. Update lead score
        # 6. Determine next state
```

## Tool Definitions Format

Each tool is defined with:

```python
{
    "type": "function",
    "function": {
        "name": "search_properties",
        "description": "Busca propiedades en la base de datos...",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Ciudad o zona (ej: 'Posadas')"
                },
                "budget_max": {
                    "type": "number",
                    "description": "Presupuesto máximo en USD"
                }
            },
            "required": []
        }
    }
}
```

## Error Handling

The system handles several error scenarios:

1. **API unavailable (503)**: Returns fallback message
2. **Timeout**: Returns timeout message  
3. **Invalid tool call**: Returns error, continues conversation
4. **Max tool calls reached**: Returns partial response with warning

## Router Integration

The Router uses a hybrid approach:

- **Fast Path**: GREETING, HUMAN_HANDOFF → Direct response (no LLM)
- **Agent Path**: PROPERTY_SEARCH, PROPERTY_DETAILS, etc. → Full agent with MiniMax M2.5

This balances:
- **Latency**: Fast path for simple intents (~50ms)
- **Capability**: Full agent for complex conversations
- **Cost**: Minimizes LLM calls for common simple intents

## Testing

Run tests:
```bash
docker-compose exec app python -m pytest tests/test_agent.py -v
```

Key test scenarios:
- LLM client parsing (with/without tool calls)
- Tool execution with mocks
- Full conversation flow
- Error handling

## Debugging

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check tool calls:
```python
logger.info(f"Tool call: {tool_name} con args: {tool_args}")
```

## Tips for Production

1. **Monitor token usage**: Check `response.usage` for cost tracking
2. **Set appropriate temperature**: 0.7 for balanced responses
3. **Limit tool calls**: Max 5 iterations prevents infinite loops
4. **Cache common searches**: Reduce DB load for popular queries
5. **Graceful degradation**: Always have fallback when LLM unavailable