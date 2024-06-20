from datetime import datetime
from flask import Flask, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import json
from linebot.v3 import WebhookHandler
from time import strftime
from linebot.v3.webhooks import FollowEvent
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi,  ReplyMessageRequest, TextMessage

app = Flask(__name__)

with open('pet_env.json') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])

# ---------------MongoDB Connect---------------
uri = mongo_uri = env['MONGO_URI']

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
db = client['pet']
people_collection = db['users']
pets_collection = db['petfile']

class LineNotifyManager:
    def __init__(self, env, people_collection, pets_collection, redirect_uri):
        self.token = None
        self.client_id = env['NOTIFY_CLIENT_ID']
        self.client_secret = env['NOTIFY_CLIENT_SECRET']
        self.people_collection = people_collection
        self.pets_collection = pets_collection
        self.redirect_uri = redirect_uri

    def send(self, message):
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'message': message
        }
        response = requests.post('https://notify-api.line.me/api/notify', headers=headers, data=data)
        return response

    def get_notify_token(self, authorize_code):
        body = {
            "grant_type": "authorization_code",
            "code": authorize_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        r = requests.post("https://notify-bot.line.me/oauth/token", data=body)
        return r.json().get("access_token")

    def update_user_notify_token(self, user_id, token):
        try:
            self.people_collection.update_one({"user_id": user_id}, {"$set": {"notify_token": token}})
        except Exception as e:
            print(f"Error updating notify token: {e}")

    def authorize(self, user_id):
        auth_url = (
            f'https://notify-bot.line.me/oauth/authorize?'
            f'response_type=code&client_id={self.client_id}&'
            f'redirect_uri={self.redirect_uri}&scope=notify&state={user_id}'
        )
        return redirect(auth_url)

    def notify_callback(self, authorize_code, user_id):
        token = self.get_notify_token(authorize_code)
        print("我的 token: " + token)
        if user_id:
            self.update_user_notify_token(user_id, token)
            self.token = token  # 更新 token
            self.send("恭喜你連動完成")
        return "恭喜你，連動完成"

    def get_user_notify_token(self, user_id):
        try:
            user_doc = self.people_collection.find_one({"user_id": user_id})
            if user_doc and "notify_token" in user_doc:
                return user_doc["notify_token"]
            else:
                return None
        except Exception as e:
            print(f"Error fetching user notify token: {e}")
            return None

    def send_notify_message(self, token, msg):
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {'message': msg}
        r = requests.post("https://notify-api.line.me/api/notify", headers=headers, data=payload)
        return r.status_code

    def check_and_send_notifications(self):
        today = datetime.now().strftime('%Y-%m-%d')
        pets_to_notify = self.pets_collection.find({"n_va_re": today})
        print(f"检查到 {pets_to_notify.count()} 个需要通知的宠物")
        for pet in pets_to_notify:
            user_id = pet['user_id']
            token = self.get_user_notify_token(user_id)
            if token:
                message = f"提醒通知: 您的宠物 {pet['p_n']} 需要在今天进行疫苗注射。"
                status = self.send_notify_message(token, message)
                print(f"已发送通知: {message}, 状态: {status}")
            else:
                print(f"未找到用户 {user_id} 的通知 token")

    def schedule_notifications(self):
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=self.check_and_send_notifications, trigger="interval", days=1)
        scheduler.start()

REDIRECT_URI = 'YOUR_REDIRECT_URI'

line_notify_manager = LineNotifyManager(env, people_collection, pets_collection, REDIRECT_URI)

@app.route('/line_notify_authorize')
def authorize():
    user_id = request.args.get('user_id')
    return line_notify_manager.authorize(user_id)

@app.route('/notify_callback', methods=['GET'])
def notify_callback():
    authorize_code = request.args.get('code')
    user_id = request.args.get('state')
    return line_notify_manager.notify_callback(authorize_code, user_id)

@handler.add(FollowEvent)
def handle_follow(event):
    userid = event.source.user_id
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        profile = line_bot_api.get_profile(userid)
        # 插入到 MongoDB
        u = dict(profile)
        u['_id'] = userid
        u['follow'] = strftime('%Y/%m/%d-%H:%M:%S')
        u['unfollow'] = None
        
        # 处理数据库操作
        try:
            people_collection.insert_one(u)
        except Exception as e:
            app.logger.error(e)
        
        welcome = f'Hello! {profile.display_name}, 歡迎使用 毛起來健檢!'
        
        # 检查用户是否已绑定 Line Notify
        user_doc = people_collection.find_one({"_id": userid})
        if user_doc and "notify_token" not in user_doc:
            subscription_url = f"https://notify-bot.line.me/oauth/authorize?response_type=code&client_id={env['NOTIFY_CLIENT_ID']}&redirect_uri={REDIRECT_URI}&scope=notify&state={userid}"
            welcome += f"\n請點擊以下鏈接來訂閱 Line Notify: {subscription_url}"

        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome)]
            )
        )

if __name__ == "__main__":
    line_notify_manager.schedule_notifications()
    app.run()
