from datetime import datetime
from flask import Flask, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import json
from linebot.v3 import WebhookHandler
from time import strftime
from linebot.v3.webhooks import FollowEvent
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi,  ReplyMessageRequest, TextMessage



with open('weilinebot.json') as f:
    env = json.load(f)  
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])


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
        print(f"检查到 {pets_to_notify.count()} 个需要通知的寵物")
        for pet in pets_to_notify:
            user_id = pet['user_id']
            token = self.get_user_notify_token(user_id)
            if token:
                message = f"提醒通知: 您的寵物 {pet['p_n']} 需要在今天進行疫苗注射。"
                status = self.send_notify_message(token, message)
                print(f"已发送通知: {message}, 狀態: {status}")
            else:
                print(f"未找到用户 {user_id} 的通知 token")

    def schedule_notifications(self):
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=self.check_and_send_notifications, trigger="interval", days=1)
        scheduler.start()


