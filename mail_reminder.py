import os
import json
from  flask import Flask
from pymongo import MongoClient
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)

# ============================================================== modify here
# MongoDB 連接設置
current_script_dir = os.getcwd()
json_file_path = os.path.join(current_script_dir, 'pet_env.json')
with open(json_file_path, 'r') as f:
    env = json.load(f)
url = env['MONGO_URI']
# ============================================================== modify here
mongo_client = MongoClient(url)
try:
    mongo_client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
db = mongo_client['pet']
users_collection = db['users']
pets_collection = db['petfile']

# Google Gmail SMTP 設置
gmail_user = 'petcarewy@gmail.com'
gmail_password = 'qjecpaojdaswjssg'

# ============================================================== modify here
@app.route('/pet/send_vaccine_reminders', methods=['GET'])
# ============================================================== modify here
def send_vaccine_reminders():  
    today = datetime.now()
    # reminder_date = today + timedelta(days=14)
    # 測試今日發送
    reminder_date = today

    # 查詢petfile集合中的n_va_re日期為14天後的文件
    pets_due_for_vaccine = pets_collection.find({'n_va_re': reminder_date.strftime('%Y-%m-%d')})
    print(pets_due_for_vaccine)

    for pet in pets_due_for_vaccine:
        user = users_collection.find_one({'user_id': pet['user_id']})
        print(user)
        if user:
            send_email(user['email'], pet['p_n'], pet['n_va_re'])

    return "Vaccine reminders sent!"

def send_email(to_email, pet_name, vaccine_date):
    subject = "寵物疫苗提醒"
    body = f"親愛的寵物主人，\n\n這是一封提醒信，您的寵物 {pet_name} 預定在 {vaccine_date} 進行疫苗接種。請確保提前安排好相關事宜。\n\n此致\n寵物照護團隊"

    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        text = msg.as_string()
        server.sendmail(gmail_user, to_email, text)
        server.quit()
        print(f"Email sent to {to_email}!")
    except Exception as e:
        print(f"Failed to send email to {to_email}. Error: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True)
