import asyncio
import json
import websockets
import os
from supabase import create_client
import bcrypt

# === ПОДКЛЮЧЕНИЕ К SUPABASE ===
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ОШИБКА] SUPABASE_URL или SUPABASE_KEY не заданы")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[OK] Supabase подключён: {SUPABASE_URL}")

# === ИГРОВЫЕ ДАННЫЕ ===
PLAYERS = {}

round_state = "countdown"
countdown_value = 3
round_time_left = 180


# === ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ===

def register_player(nickname, password):
    """Создать нового игрока. Возвращает (успех, сообщение)."""
    if supabase is None:
        return False, "База не подключена"

    # Проверяем, есть ли уже такой ник
    existing = supabase.table("users").select("id").eq("nickname", nickname).execute()
    if existing.data:
        return False, "Этот ник уже занят"

    # Хешируем пароль
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # Создаём запись
    try:
        supabase.table("users").insert({
            "nickname": nickname,
            "password_hash": password_hash
        }).execute()
        return True, "Регистрация успешна"
    except Exception as e:
        return False, f"Ошибка базы: {e}"


def login_player(nickname, password):
    """Проверить логин и пароль. Возвращает (успех, сообщение)."""
    if supabase is None:
        return False, "База не подключена"

    # Ищем игрока
    result = supabase.table("users").select("*").eq("nickname", nickname).execute()
    if not result.data:
        return False, "Игрок не найден"

    player = result.data[0]
    stored_hash = player["password_hash"].encode()

    # Проверяем пароль
    if bcrypt.checkpw(password.encode(), stored_hash):
        return True, "Вход выполнен"
    else:
        return False, "Неверный пароль"


# === ИГРОВОЙ ЦИКЛ ===

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
                    for p in PLAYERS.values():
                        p["roundDone"] = False

            elif round_state == "playing":
                if round_time_left > 0:
                    round_time_left -= 1
                else:
                    round_state = "countdown"
                    countdown_value = 3
                    round_time_left = 180

            if PLAYERS:
                players_data = [p for p in PLAYERS.values() if not p.get("roundDone", False)]
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
        "isShaman": False,
        "nickname": None,
        "logged_in": False,
        "role_code": None
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

                         # === РЕГИСТРАЦИЯ ===
                if data.get("type") == "register":
                    nickname = data.get("nickname", "").strip()
                    password = data.get("password", "")

                    if not nickname or not password:
                        await websocket.send(json.dumps({
                            "type": "register_result",
                            "success": False,
                            "message": "Заполните все поля",
                            "nickname": None
                        }))
                        continue

                    success, msg = register_player(nickname, password)
                    role_code = None
                    if success:
                        PLAYERS[websocket]["nickname"] = nickname
                        PLAYERS[websocket]["logged_in"] = True
                        PLAYERS[websocket]["id"] = nickname
                        user_row = supabase.table("users").select("role_code").eq("nickname", nickname).execute()
                        if user_row.data:
                            role_code = user_row.data[0].get("role_code")
                        PLAYERS[websocket]["role_code"] = role_code

                    await websocket.send(json.dumps({
                        "type": "register_result",
                        "success": success,
                        "message": msg,
                        "nickname": nickname if success else None,
                        "role_code": role_code
                    }))
                    continue

                              # === ЛОГИН ===
                if data.get("type") == "login":
                    nickname = data.get("nickname", "").strip()
                    password = data.get("password", "")

                    if not nickname or not password:
                        await websocket.send(json.dumps({
                            "type": "login_result",
                            "success": False,
                            "message": "Заполните все поля",
                            "nickname": None
                        }))
                        continue

                    success, msg = login_player(nickname, password)
                    role_code = None
                    if success:
                        PLAYERS[websocket]["nickname"] = nickname
                        PLAYERS[websocket]["logged_in"] = True
                        PLAYERS[websocket]["id"] = nickname
                        user_row = supabase.table("users").select("role_code").eq("nickname", nickname).execute()
                        if user_row.data:
                            role_code = user_row.data[0].get("role_code")
                        PLAYERS[websocket]["role_code"] = role_code

                    await websocket.send(json.dumps({
                        "type": "login_result",
                        "success": success,
                        "message": msg,
                        "nickname": nickname if success else None,
                        "role_code": role_code
                    }))
                    continue

                # === СДАЧА СЫРА ===
                if data.get("action") == "deliver":
                    PLAYERS[websocket]["hasCheese"] = False
                    PLAYERS[websocket]["cheese_delivered"] += 1
                    PLAYERS[websocket]["roundDone"] = True
                    PLAYERS[websocket]["x"] = 100
                    PLAYERS[websocket]["y"] = 300

                    if PLAYERS:
                        players_data = [p for p in PLAYERS.values() if not p.get("roundDone", False)]
                        await broadcast({
                            "type": "update",
                            "players": players_data,
                            "roundState": round_state,
                            "countdownValue": countdown_value,
                            "roundTime": round_time_left
                        })

                    if PLAYERS and all(p.get("roundDone", False) for p in PLAYERS.values()):
                        round_state = "countdown"
                        countdown_value = 3
                        round_time_left = 180
                    continue

                # === ОБЫЧНОЕ ОБНОВЛЕНИЕ ===
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
