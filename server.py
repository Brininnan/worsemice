import asyncio
import json
import websockets
import os

PLAYERS = {}

round_state = "countdown"
countdown_value = 3
round_time_left = 180


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
                    round_time_left = 180
                    # Сброс флагов раунда у всех
                    for p in PLAYERS.values():
                        p["roundDone"] = False
            elif round_state == "playing":
                if round_time_left > 0:
                    round_time_left -= 1
                else:
                    round_state = "countdown"
                    countdown_value = 3
                    round_time_left = 180   # ← СБРОС СРАЗУ

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
    if not PLAYERS:
        return
    targets = [ws for ws in PLAYERS.keys() if ws != exclude]
    dead = []
    for ws in targets:
        try:
            await ws.send(json.dumps(message))
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in PLAYERS:
            print(f"[-] Мёртвый сокет удалён: {PLAYERS[ws].get('id')}")
            del PLAYERS[ws]


async def handle_player(websocket):
    global round_state, countdown_value, round_time_left
    player_id = str(id(websocket))

    PLAYERS[websocket] = {
        "id": f"Mouse_{player_id[-4:]}",
        "x": 100,
        "y": 300,
        "facingRight": True,
        "hasCheese": False,
        "cheese_delivered": 0,
        "roundDone": False,
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
            "id": PLAYERS[websocket]["id"],
            "players": current_players_data,
            "roundState": round_state,
            "countdownValue": countdown_value,
            "roundTime": round_time_left
        }))

        async for message in websocket:
            try:
                data = json.loads(message)

                # === ОБРАБОТКА СДАЧИ СЫРА ===
                if data.get("action") == "deliver":
                    PLAYERS[websocket]["hasCheese"] = False
                    PLAYERS[websocket]["cheese_delivered"] += 1
                    PLAYERS[websocket]["roundDone"] = True

                    # Все сдали?
                    if PLAYERS and all(p.get("roundDone", False) for p in PLAYERS.values()):
                        round_state = "countdown"
                        countdown_value = 3
                        round_time_left = 180   # ← СБРОС
                    continue

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
    print(f"=== Сервер WorseMice запущен на порту {port} ===")

    async with websockets.serve(handle_player, host, port):
        asyncio.create_task(game_loop())
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n=== Сервер остановлен ===")
