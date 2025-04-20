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
from datetime import datetime
import uuid

# .envファイルをロード
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SYSTEM_SHEET_URL")

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS_PATH")
SPREADSHEET_NAME = "清算スプシ"

GAS_BASE_URL = os.getenv("GAS_BASE_URL")
CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=confirm"
All_CONFIRM_SCRIPT_URL = GAS_BASE_URL + "?action=all_confirm"

credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPES)
gc = gspread.authorize(credentials)
sheet = gc.open(SPREADSHEET_NAME).sheet1

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@bot.event
async def on_ready():
    print(f'ログインしました: {bot.user}')

@bot.command()
async def memo(ctx, amount: int):
    confirm_message = None
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
        nonlocal confirm_message

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

                    elif label in ["記帳", "全額記帳"]:
                        unique_id = f"ID-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
                        await asyncio.get_running_loop().run_in_executor(None, sheet.update, 'E5', [[unique_id]])
                        if label == "記帳":
                            requests.get(CONFIRM_SCRIPT_URL)
                        else:
                            requests.get(All_CONFIRM_SCRIPT_URL)

                        await interaction.message.edit(view=None)
                        view2 = discord.ui.View()
                        view2.add_item(discord.ui.Button(label="記帳確認", style=discord.ButtonStyle.link, url=SPREADSHEET_URL))

                        delete_button = discord.ui.Button(label="記帳削除", style=discord.ButtonStyle.danger)

                        async def delete_callback(interaction):
                            try:
                                # まず普通に削除を試みる
                                target_id = sheet.acell("E5").value
                                all_rows = sheet.get_all_values()
                                for idx, row in enumerate(all_rows[8:], start=9):
                                    if len(row) >= 5 and row[4] and row[4].startswith(target_id):
                                        sheet.delete_rows(idx)
                                        await interaction.response.send_message("記帳を削除したよ！")
                                        return
                                await interaction.response.send_message("削除対象のIDが見つからなかったよ！")
                            except discord.errors.InteractionResponded:
                                # インタラクションが期限切れだった場合
                                view_retry = discord.ui.View()
                                new_delete_button = discord.ui.Button(label="記帳削除（再試行）", style=discord.ButtonStyle.danger)

                                async def retry_delete_callback(new_interaction):
                                    target_id = sheet.acell("E5").value
                                    all_rows = sheet.get_all_values()
                                    for idx, row in enumerate(all_rows[8:], start=9):
                                        if len(row) >= 5 and row[4] and row[4].startswith(target_id):
                                            sheet.delete_rows(idx)
                                            await new_interaction.response.send_message("記帳を削除したよ！（再試行）")
                                            return
                                    await new_interaction.response.send_message("削除対象のIDが見つからなかったよ！（再試行）")

                                new_delete_button.callback = retry_delete_callback
                                view_retry.add_item(new_delete_button)

                                await interaction.channel.send("❗このボタンは期限切れだよ！新しいボタンを押してね！", view=view_retry)

                        delete_button.callback = delete_callback
                        view2.add_item(delete_button)

                        delete_button = discord.ui.Button(label="記帳削除", style=discord.ButtonStyle.danger)

                        async def delete_callback(delete_interaction):
                            try:
                                target_id = sheet.acell("E5").value
                                all_rows = sheet.get_all_values()
                                found = False
                                for idx, row in enumerate(all_rows[8:], start=9):
                                    if len(row) >= 5 and target_id in row[4]:
                                        sheet.delete_rows(idx)
                                        await delete_interaction.response.send_message("記帳を削除したよ！")
                                        found = True
                                        break
                                if not found:
                                    await delete_interaction.response.send_message("該当する記帳が見つからなかったよ！")
                            except Exception as e:
                                await delete_interaction.response.send_message(f"エラーが発生したよ！: {e}")

                        delete_button.callback = delete_callback
                        view2.add_item(delete_button)

                        await interaction.followup.send(f"{label}したよ！", view=view2)
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
