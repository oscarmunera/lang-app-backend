from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROMPTS = {
    "hijo": {
        "instruction": "Eres Léo, un tutor de francés para niños. Habla muy despacio, usa frases de máximo 5 palabras y muchos ánimos.",
        "model": "gemini-2.0-flash-exp"
    },
    "adulto": {
        "instruction": "You are a native English partner. Focus on natural fluency. Correct errors subtly in your next sentence.",
        "model": "gemini-2.0-flash-exp"
    }
}

@app.get("/config/{profile}")
async def get_config(profile: str):
    if profile not in PROMPTS:
        raise HTTPException(status_code=404, detail="Profile not found")
    return PROMPTS[profile]

@app.get("/health")
def health():
    return {"status": "ok"}
