from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import websockets
import json
import os
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ API Key SOLO en el backend, nunca en el frontend
# En FastAPI Cloud: agrega GEMINI_API_KEY como variable de entorno
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

PROFILES = {
    "hijo": {
        "instruction": "Eres Léo, un tutor de francés paciente y divertido para niños. Habla muy despacio. Usa frases cortas y sencillas. Siempre anima al niño con entusiasmo. Responde SIEMPRE en francés, pero si el niño habla español, entiéndelo y respóndele en francés simple.",
        "model": "gemini-2.5-flash-preview-05-20",
        "lang": "fr-FR"
    },
    "adulto": {
        "instruction": "You are a friendly native English conversation partner. Your goal is to help the user improve their fluency. Keep conversations natural and engaging. When the user makes an error, don't correct it directly — instead, use the correct form naturally in your next sentence. Ask follow-up questions to keep the conversation flowing.",
        "model": "gemini-2.5-flash-preview-05-20",
        "lang": "en-US"
    }
}

GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


@app.get("/config/{profile}")
async def get_config(profile: str):
    """Devuelve metadata del perfil (sin API key ni instrucciones sensibles)."""
    if profile not in PROFILES:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {
        "lang": PROFILES[profile]["lang"],
        "profile": profile
    }


@app.websocket("/session/{profile}")
async def session_proxy(websocket: WebSocket, profile: str):
    """
    Proxy WebSocket seguro: 
    Frontend <-> Este backend <-> Gemini Live API
    La API key NUNCA sale del servidor.
    """
    if profile not in PROFILES:
        await websocket.close(code=4004)
        return

    if not GEMINI_API_KEY:
        await websocket.close(code=4003)
        return

    await websocket.accept()

    config = PROFILES[profile]
    gemini_url = f"{GEMINI_WS_URL}?key={GEMINI_API_KEY}"

    try:
        async with websockets.connect(gemini_url) as gemini_ws:

            # 1. Enviar configuración inicial a Gemini
            setup_msg = {
                "setup": {
                    "model": f"models/{config['model']}",
                    "system_instruction": {
                        "parts": [{"text": config["instruction"]}]
                    },
                    "generation_config": {
                        "response_modalities": ["TEXT"]
                    }
                }
            }
            await gemini_ws.send(json.dumps(setup_msg))

            # 2. Relay bidireccional: frontend <-> Gemini
            async def frontend_to_gemini():
                """Reenvía mensajes del frontend a Gemini."""
                try:
                    while True:
                        data = await websocket.receive_text()
                        await gemini_ws.send(data)
                except WebSocketDisconnect:
                    pass

            async def gemini_to_frontend():
                """Reenvía respuestas de Gemini al frontend."""
                try:
                    async for message in gemini_ws:
                        await websocket.send_text(message)
                except Exception:
                    pass

            # Correr ambas direcciones en paralelo
            await asyncio.gather(
                frontend_to_gemini(),
                gemini_to_frontend()
            )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/health")
def health():
    return {
        "status": "ok",
        "gemini_key_configured": bool(GEMINI_API_KEY)
    }