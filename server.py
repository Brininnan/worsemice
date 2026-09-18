import asyncio
import json
import websockets
import os

# Словарь для хранения подключенных игроков
PLAYERS = {}

# Состояние раунда и таймеры
round_state = "countdown"  # "countdown" или "playing"
countdown_value = 3        # Отсчет 3, 2, 1
round_time_left = 180      # Длительность раунда в секундах

async def game_loop():
    global round_state, countdown_value, round_time_left
    counter = 0
    while True:
        await asyncio.sleep(0.05)
        counter += 0.05
        
        if counter >= 1.0:
            counter = 0
            if round_state == "countdown":
                countdown_value -= 1
                if countdown_value <= 0:
                    round_state = "playing"
                    round_time_left = 180  # Сброс на 3 минуты при начале игры
            elif round_state == "playing":
                if round_time_left > 0:
                    round_time_left -= 1
                else:
                    round_state = "countdown"
                    countdown_value = 3

            if PLAYERS:
                players_data = list(PLAYERS.values())
                await broadcast({
                    "type": "update",
                    "players": players_data,
                    "roundState": round_state,
                    "countdownValue": countdown_value,
                    "roundTime": round_time_left
                })

async def broadcast(message, exclude=None):
    """Отправка сообщения всем подключенным игрокам."""
    if not PLAYERS:
        return
    targets = [ws for ws in PLAYERS.keys() if ws != exclude]
    if targets:
        await asyncio.gather(
            *[ws.send(json.dumps(message)) for ws in targets],
            return_exceptions=True
        )

async def handle_player(websocket):
    """Обработка одного игрока от подключения до отключения."""
    player_id = str(id(websocket))

    PLAYERS[websocket] = {
        "id": player_id,
        "x": 100,
        "y": 300,
        "facingRight": True,
        "hasCheese": False,
        "isMoving": False,
        "idleState": 0,
        "isAirborne": False,
        "emotion": None,
        "nickname": f"Mouse_{player_id[-4:]}"
    }

    print(f"[+] Игрок подключился: {player_id}")

    try:
        current_players_data = list(PLAYERS.values())
        await websocket.send(json.dumps({
            "type": "init",
            "id": player_id,
            "players": current_players_data,
            "roundState": round_state,
            "countdownValue": countdown_value,
            "roundTime": round_time_left
        }))

        async for message in websocket:
            try:
                data = json.loads(message)
                PLAYERS[websocket]["x"] = data.get("x", PLAYERS[websocket]["x"])
                PLAYERS[websocket]["y"] = data.get("y", PLAYERS[websocket]["y"])
                PLAYERS[websocket]["facingRight"] = data.get("facingRight", PLAYERS[websocket]["facingRight"])
                PLAYERS[websocket]["hasCheese"] = data.get("hasCheese", PLAYERS[websocket]["hasCheese"])
                PLAYERS[websocket]["isMoving"] = data.get("isMoving", PLAYERS[websocket]["isMoving"])
                PLAYERS[websocket]["idleState"] = data.get("idleState", PLAYERS[websocket]["idleState"])
                PLAYERS[websocket]["isAirborne"] = data.get("isAirborne", PLAYERS[websocket]["isAirborne"])
                PLAYERS[websocket]["emotion"] = data.get("emotion", PLAYERS[websocket]["emotion"])
            except json.JSONDecodeError:
                print(f"[!] Ошибка декодирования JSON от {player_id}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in PLAYERS:
            del PLAYERS[websocket]
            print(f"[-] Игрок отключился: {player_id}")

async def main():
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8765))
    print(f"=== Сервер WorseMice запущен на ws://localhost:{port} ===")
    
    async with websockets.serve(handle_player, host, port):
        asyncio.create_task(game_loop())
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n=== Сервер остановлен ===")
