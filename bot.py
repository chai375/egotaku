import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import asyncio

from dotenv import load_dotenv
import os

# .envファイルをロード
load_dotenv()

# 環境変数からトークンを取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Google Sheets APIの設定
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS_PATH")  # 認証情報のJSONファイル
SPREADSHEET_NAME = "清算スプシ"

# Google Apps Script のURL
GAS_BASE_URL = os.getenv("GAS_BASE_URL")
CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=confirm"
All_CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=all_confirm"

# Google Sheetsへの接続
credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
gc = gspread.authorize(credentials)
sheet = gc.open(SPREADSHEET_NAME).sheet1  # 1つ目のシートを開く

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'ログインしました: {bot.user}')

@bot.command()
async def memo(ctx, amount: int):
    user_name = ctx.author.display_name  # ユーザー名取得

       # ✅ Discord名とスプレッドシートの値を対応付ける辞書を追加
    name_mapping = {
        "ちょい": "ちゃい",
      "こしたみん": "こし"
   }
    
    sheet_name = name_mapping.get(user_name, user_name)  # 変換後の名前を取得
    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'B5', [[sheet_name]])
    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'C5', [[amount]])
    
    await ctx.send(f"{user_name} さん、どのような用途で使用しましたか？")
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel
    
    response = await bot.wait_for('message', check=check)

    # ✅ 用途入力後のキャンセル処理
    if response.content.strip() == "キャンセル":
           await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
           await ctx.send("入力をキャンセルしたよ！")
           return
    
    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'D5', [[response.content]])

    async def show_confirmation():
        b5 = sheet.acell("B5").value
        c5 = sheet.acell("C5").value
        d5 = sheet.acell("D5").value
        confirm_msg = f"確認してください！\n名前: {b5}\n金額: {c5}\n内容: {d5}"
        view = discord.ui.View()
        button_labels = ["金額修正", "内容修正", "記帳", "全額記帳"]
        for label in button_labels:
            style = discord.ButtonStyle.secondary
            if label == "記帳":
                style = discord.ButtonStyle.primary
            elif label == "全額記帳":
                style = discord.ButtonStyle.danger

            button = discord.ui.Button(label=label, style=style)

            async def make_callback(label):
                async def callback(interaction):
                    await interaction.response.defer()
                    if label == "金額修正":
                        await interaction.followup.send("新しい金額を入力してね！")
                        new_msg = await bot.wait_for("message", check=check)
                        if new_msg.content.strip() == "キャンセル":
                            await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
                            await interaction.followup.send("入力をキャンセルしたよ！")
                            return
                        await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'C5', [[new_msg.content]])
                        await show_confirmation()

                    elif label == "内容修正":
                        await interaction.followup.send("新しい内容を入力してね！")
                        new_msg = await bot.wait_for("message", check=check)
                        if new_msg.content.strip() == "キャンセル":
                            await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
                            await interaction.followup.send("入力をキャンセルしたよ！")
                            return
                        await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'D5', [[new_msg.content]])
                        await show_confirmation()

                    elif label == "記帳":
                        requests.get(CONFIRM_SCRIPT_URL)
                        await interaction.followup.send("記帳しました！")
                        return
                    elif label == "全額記帳":
                        requests.get(All_CONFIRM_SCRIPT_URL)
                        await interaction.followup.send("全額記帳しました！")
                        return
                return callback

            button.callback = await make_callback(label)
            view.add_item(button)

        await ctx.send(confirm_msg, view=view)

    await show_confirmation()

    # ✅ 「確認してください」のあとにキャンセルしたい場合も対応！
    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        if msg.content.strip() == "キャンセル":
            await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
            await ctx.send("入力をキャンセルしたよ！")
            return
    except asyncio.TimeoutError:
        pass

from flask import Flask, request
import threading

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data and "content" in data:
        # ここで任意のチャンネルに送信（チャンネルIDは .env から取得がオススメ）
        channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
        message = data["content"]

        channel = bot.get_channel(channel_id)
        if channel:
            asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop)
        return "OK", 200
    return "Invalid", 400

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    bot.run(DISCORD_BOT_TOKEN)
