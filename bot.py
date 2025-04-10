import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import asyncio
import re
from flask import Flask, request
import threading
from dotenv import load_dotenv
import os

# .envファイルをロード
load_dotenv()

# 環境変数からトークンを取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SYSTEM_SHEET_URL")

# Google Sheets APIの設定
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS_PATH")
SPREADSHEET_NAME = "清算スプシ"

# Google Apps Script のURL
GAS_BASE_URL = os.getenv("GAS_BASE_URL")
CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=confirm"
All_CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=all_confirm"

# Google Sheetsへの接続
credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
gc = gspread.authorize(credentials)
sheet = gc.open(SPREADSHEET_NAME).sheet1

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'ログインしました: {bot.user}')

@bot.command()
async def memo(ctx, amount: int):
    user_name = ctx.author.display_name
    name_mapping = {
        "ちょい": "ちゃい",
        "こしたみん": "こし"
    }
    sheet_name = name_mapping.get(user_name, user_name)
    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'B5', [[sheet_name]])
    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'C5', [[amount]])

    await ctx.send(f"{user_name} さん、どんな用途で使用したの？")

    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    response = await bot.wait_for('message', check=check)

    if response.content.strip() == "キャンセル":
        await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
        await ctx.send("入力をキャンセルしたよ！")
        return

    await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'D5', [[response.content]])

    async def show_confirmation():
        b5 = sheet.acell("B5").value
        c5 = int(sheet.acell("C5").value)
        d5 = sheet.acell("D5").value
        c5_formatted = f"【 {c5:,} 】"
        confirm_msg = f"確認してね！\n名前: {b5}\n金額: {c5_formatted}円\n内容: {d5}"

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
                        await confirm_message.edit(view=None)
                        view2 = discord.ui.View()
                        view2.add_item(discord.ui.Button(label="記帳確認", style=discord.ButtonStyle.link, url=SPREADSHEET_URL))
                        await interaction.followup.send("記帳したよ！", view=view2)
                        return
                    elif label == "全額記帳":
                        requests.get(All_CONFIRM_SCRIPT_URL)
                        await confirm_message.edit(view=None)
                        view2 = discord.ui.View()
                        view2.add_item(discord.ui.Button(label="記帳確認", style=discord.ButtonStyle.link, url=SPREADSHEET_URL))
                        await interaction.followup.send("全額記帳したよ！", view=view2)
                        return
                return callback

            button.callback = await make_callback(label)
            view.add_item(button)

        confirm_message = await ctx.send(confirm_msg, view=view)

    await show_confirmation()

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        if msg.content.strip() == "キャンセル":
            await asyncio.get_running_loop().run_in_executor(None, sheet.batch_clear, ['A5:E5'])
            await ctx.send("入力をキャンセルしたよ！")
            return
    except asyncio.TimeoutError:
        pass

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        content = message.content.replace(f"<@{bot.user.id}>", "").strip()
        match = re.match(r"^\d{1,10}$", content)
        if match:
            ctx = await bot.get_context(message)
            await memo(ctx, int(content))
            return

    await bot.process_commands(message)

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data and "content" in data:
        channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
        message = data["content"]
        sheet_url = data.get("sheet_url")

        async def send_notification():
            channel = bot.get_channel(channel_id)
            if not channel:
                print("チャンネルが見つからなかったよ")
                return

            if sheet_url:
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="決算を見る", style=discord.ButtonStyle.link, url=sheet_url))
                await channel.send(content=message, view=view)
            else:
                await channel.send(content=message)

        asyncio.run_coroutine_threadsafe(send_notification(), bot.loop)
        return "OK", 200

    return "Invalid", 400

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    bot.run(DISCORD_BOT_TOKEN)
