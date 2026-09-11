import asyncio
import json
import websockets

# Словарь, где мы будем хранить координаты всех подключенных игроков
# Формат: { socket_объект: {"id": "player1", "x": 100, "y": 300} }
connected_players = {}
player_counter = 0

async def handle_client(websocket):
    global player_counter
    
    # 1. Придумываем уникальный ID для зашедшего игрока
    player_counter += 1
    player_id = f"Mice_{player_counter}"
    
    # Запоминаем нового игрока на сервере с начальными координатами
    connected_players[websocket] = {"id": player_id, "x": 100, "y": 300}
    print(f"[ПОДКЛЮЧЕНИЕ] Игрок {player_id} зашел в игру!")

    try:
        # 2. Постоянно слушаем сообщения от этого конкретного игрока
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Обновляем координаты этого игрока в нашей базе на сервере
                connected_players[websocket]["x"] = data.get("x", 100)
                connected_players[websocket]["y"] = data.get("y", 300)
                
                # 3. Собираем список координат ВСЕХ игроков на сервере
                all_players_data = list(connected_players.values())
                
                # 4. Рассылаем этот список абсолютно ВСЕМ подключенным браузерам
                # Чтобы они увидели чужие мышки на своих экранах
                message_to_send = json.dumps({"players": all_players_data})
                
                # Метод websockets.broadcast отправляет данные сразу всем сокетам в списке
                websockets.broadcast(connected_players.keys(), message_to_send)
                
            except json.JSONDecodeError:
                pass # Игнорируем, если прилетел сломанный текст

    except websockets.exceptions.ConnectionClosed:
        pass
    
    finally:
        # 5. Если игрок закрыл вкладку или вышел из игры — удаляем его с сервера
        print(f"[ВЫХОД] Игрок {player_id} покинул комнату.")
        del connected_players[websocket]

async def main():
    # Запускаем сервер на вашем компьютере на порту 8001
    # 0.0.0.0 означает, что сервер будет слушать любые подключения
    async with websockets.serve(handle_client, "0.0.0.0", 8001):
        print("====== ИГРОВОЙ СЕРВЕР WORSEMICE ЗАПУЩЕН ======")
        print("Слушаю подключения на порту 8001...")
        await asyncio.Future() # Заставляем сервер работать бесконечно

if __name__ == "__main__":
    asyncio.run(main())
