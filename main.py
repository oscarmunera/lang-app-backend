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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Modelo y URL verificados en documentación oficial de Google (marzo 2026)
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
GEMINI_WS_URL = (
    "wss://generativelanguage.googleapis.com"
    "/ws/google.ai.generativelanguage.v1beta"
    ".GenerativeService.BidiGenerateContent"
)

PROFILES = {
    "hijo": {
        "instruction": (
            "Eres Léo, un tutor de francés paciente y divertido para niños. "
            "Habla muy despacio. Usa frases cortas y sencillas. "
            "Siempre anima al niño con entusiasmo. "
            "Responde SIEMPRE en francés, pero si el niño habla español, "
            "entiéndelo y respóndele en francés simple."
        ),
        "lang": "fr-FR"
    },
    "adulto": {
        "instruction": (
            "You are a friendly native English conversation partner. "
            "Your goal is to help the user improve their fluency. "
            "Keep conversations natural and engaging. "
            "When the user makes an error, don't correct it directly — "
            "instead, use the correct form naturally in your next sentence. "
            "Ask follow-up questions to keep the conversation flowing."
        ),
        "lang": "en-US"
    }
}


@app.get("/config/{profile}")
async def get_config(profile: str):
    if profile not in PROFILES:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {"lang": PROFILES[profile]["lang"], "profile": profile}


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

    gemini_url = f"{GEMINI_WS_URL}?key={GEMINI_API_KEY}"
    config = PROFILES[profile]

    try:
        async with websockets.connect(gemini_url) as gemini_ws:

            # ✅ Estructura exacta según documentación oficial Google
            # - clave raíz: "config" (no "setup")
            # - camelCase: responseModalities, systemInstruction
            # - modelo con prefijo "models/"
            setup_msg = {
                "config": {
                    "model": f"models/{MODEL}",
                    "responseModalities": ["AUDIO"],
                    "systemInstruction": {
                        "parts": [{"text": config["instruction"]}]
                    }
                }
            }
            await gemini_ws.send(json.dumps(setup_msg))

            # Relay bidireccional: el frontend envía audio, Gemini responde
            async def frontend_to_gemini():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await gemini_ws.send(data)
                except WebSocketDisconnect:
                    pass

            async def gemini_to_frontend():
                try:
                    async for message in gemini_ws:
                        await websocket.send_text(message)
                except Exception:
                    pass

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