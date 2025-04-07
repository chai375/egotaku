import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

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
    sheet.update('B5', [[sheet_name]]) 

    sheet.update('C5', [[amount]])
    
    await ctx.send(f"{user_name} さん、どのような用途で使用しましたか？")
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel
    
    response = await bot.wait_for('message', check=check)
    sheet.update('D5', [[response.content]])  
    
    confirm_msg = f"確認してください！\n名前: {sheet_name}\n金額: {amount}\n内容: {response.content}"
    view = discord.ui.View()
    
    button1 = discord.ui.Button(label="記帳", style=discord.ButtonStyle.primary)
    async def button1_callback(interaction):
        try:

            # まずインタラクションを遅延応答
            await interaction.response.defer()

            requests.get(CONFIRM_SCRIPT_URL)
            await interaction.followup.send("記帳しました！")
        except discord.errors.NotFound as e:
            await interaction.channel.send("インタラクションが期限切れです。もう一度試してください。")
    button1.callback = button1_callback
    
    button2 = discord.ui.Button(label="全額記帳", style=discord.ButtonStyle.danger)
    async def button2_callback(interaction):
        try:
             # まずインタラクションを遅延応答
            await interaction.response.defer()

            requests.get(All_CONFIRM_SCRIPT_URL)
            await interaction.followup.send("全額記帳しました！")
        except discord.errors.NotFound:
            await interaction.channel.send("インタラクションが期限切れです。もう一度試してください。")
    button2.callback = button2_callback
    
    view.add_item(button1)
    view.add_item(button2)
    
    await ctx.send(confirm_msg, view=view)

bot.run(DISCORD_BOT_TOKEN)
