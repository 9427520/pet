from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import json
from datetime import datetime, timedelta
from pymongo import MongoClient
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
import pytz

app = Flask(__name__)

# 載入環境變數和 MongoDB 設定
current_script_dir = os.getcwd()
json_file_path = os.path.join(current_script_dir, 'weilinebot.json')

with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])

url = "mongodb+srv://william:williamno1@williamhandsome.ov7ufje.mongodb.net/?retryWrites=true&w=majority&appName=williamhandsome"
mongo_client = MongoClient(url)
db = mongo_client['pet']
pets_collection = db['petfile']

# 設定時區
tz = pytz.timezone('Asia/Taipei')

def check_and_send_vaccine_reminders():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 計算明天的日期
        tomorrow = (datetime.now(tz) + timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"Checking for pets with vaccine reminders for date: {tomorrow}")

        # 查找所有需要提醒的寵物
        pets_to_remind = pets_collection.find({"n_va_re": tomorrow})

        for pet in pets_to_remind:
            user_id = pet["user_id"]
            pet_name = pet["p_n"]
            message_text = f"明天請記得帶 {pet_name} 打疫苗。"
            
            # 發送提醒訊息
            message = TextMessage(text=message_text)
            push_message_request = PushMessageRequest(to=user_id, messages=[message])
            response = line_bot_api.push_message(push_message_request)
            
            # 打印推送結果
            print(f"Sent reminder to user {user_id} for pet {pet_name}. Response: {response}")

scheduler = BackgroundScheduler(timezone=tz)
# 設定每天早上 9 點執行任務
scheduler.add_job(func=check_and_send_vaccine_reminders, trigger=CronTrigger(hour=12, minute=21, timezone=tz))
scheduler.start()

@app.route('/')
def home():
    return "Vaccine Reminder Service is running."

if __name__ == "__main__":
    app.run(port=5001)

