import sys
import asyncio

# Fix Windows console UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEMP_DIR = PROJECT_ROOT / "storage" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

from voice_engine_ryu import RyuVoiceAgent

async def main():
    print("--- INICIANDO PRUEBA COMPLETA DEL MOTOR DE VOZ ---")
    agent = RyuVoiceAgent(caller_phone="+52 374 117 2661", caller_name="Cliente Prueba")
    
    saludo_path = str(TEMP_DIR / "audio_1_saludo.mp3")
    print(f"\nSaludando: {agent.greeting}")
    await agent.speak(agent.greeting, saludo_path)
    print(f"Audio generado: {saludo_path}")

    turns = [
        "hola, quiero pedir unas gyosas",
        "de cerdo por favor, y es para recoger",
        "sin bebida, voy a pagar con tarjeta",
        "sí, confirmo el pedido"
    ]

    for i, user_text in enumerate(turns, start=2):
        print(f"\n[Cliente]: {user_text}")
        reply = agent.think_and_respond(user_text)
        print(f"[RyuBot]: {reply}")
        audio_file = str(TEMP_DIR / f"audio_{i}_respuesta.mp3")
        await agent.speak(reply, audio_file)
        print(f"[Audio generado]: {audio_file}")

    print(f"\nEstado de confirmación: {agent.order_confirmed}")
    print("--- PRUEBA FINALIZADA CON ÉXITO ---")

if __name__ == "__main__":
    asyncio.run(main())
