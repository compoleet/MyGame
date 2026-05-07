import asyncio
import websockets
import json

async def register():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        username = input("Username: ")
        password = input("Password: ")
        class_name = input("Class (warrior/mage): ") or "warrior"
        await ws.send(json.dumps({
            "type": "register",
            "username": username,
            "password": password,
            "class": class_name
        }))
        resp = await ws.recv()
        print(resp)

asyncio.run(register())