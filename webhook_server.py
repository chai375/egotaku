from flask import Flask, request
import discord
import asyncio

app = Flask(__name__)

# Discord Bot のクライアントをグローバルに参照できるように
discord_client = None

@app.route("/notify", methods=["POST"])
def notify():
    data = request.json
    message = data.get("message", "通知が届きました！")

    # Discord通知を非同期で送信
    if discord_client:
        asyncio.run_coroutine_threadsafe(
            discord_client.get_channel("YOUR_CHANNEL_ID").send(message),
            discord_client.loop
        )
    return "OK", 200
