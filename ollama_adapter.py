from fastapi import FastAPI, Request
import requests
import json

app = FastAPI()

# 👉 IMPORTANT: your Ollama server (secondary PC)
OLLAMA_URL = "http://192.168.1.9:11434/api/generate"
MODEL = "qwen2.5-coder:32b"

def messages_to_prompt(messages):
    prompt = ""
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        prompt += f"{role}: {content}\n"
    return prompt


# ---------------- MODELS ----------------
@app.get("/v1/models")
@app.get("/models")
async def list_models():
    return {
        "data": [
            {
                "id": "qwen-local",
                "object": "model"
            }
        ]
    }


# ---------------- CHAT ----------------
@app.post("/v1/chat/completions")
@app.post("/chat/completions")
@app.post("/api/chat")
async def chat_completions(req: Request):
    body = await req.json()
    messages = body.get("messages", [])

    prompt = messages_to_prompt(messages)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "num_predict": 512
                }
            },
            stream=True,
            timeout=600
        )

        full_response = ""

        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    full_response += data.get("response", "")
                except:
                    pass

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": full_response
                    }
                }
            ]
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------- COMPLETIONS ----------------
@app.post("/v1/completions")
@app.post("/completions")
async def completions(req: Request):
    body = await req.json()
    prompt = body.get("prompt", "")

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "num_predict": 512
                }
            },
            stream=True,
            timeout=600
        )

        full_response = ""

        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    full_response += data.get("response", "")
                except:
                    pass

        return {
            "choices": [
                {
                    "text": full_response
                }
            ]
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------- FALLBACK (CATCH ALL) ----------------
@app.api_route("/{path:path}", methods=["GET", "POST"])
async def catch_all(path: str, req: Request):
    try:
        body = await req.json()
    except:
        body = {}

    messages = body.get("messages", [])
    prompt = messages_to_prompt(messages) if messages else str(body)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "num_predict": 512
                }
            },
            stream=True,
            timeout=600
        )

        full_response = ""

        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    full_response += data.get("response", "")
                except:
                    pass

        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": full_response
                    }
                }
            ]
        }

    except Exception as e:
        return {"error": str(e)}