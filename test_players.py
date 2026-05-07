import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8765"
    username = input("Username: ")
    password = input("Password: ")
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "auth", "username": username, "password": password}))
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Received: {data}")
            if data["type"] == "init":
                my_id = data["data"]["player_id"]
                print(f"My id: {my_id}, position: ({data['data']['x']}, {data['data']['y']})")

asyncio.run(test())