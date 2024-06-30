import os
import json
from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
from google.cloud import storage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

app = Flask(__name__)

# ============================================================== 
# MongoDB 連接設置
current_script_dir = os.getcwd()
json_file_path = os.path.join(current_script_dir, 'pet_env.json')
with open(json_file_path, 'r') as f:
    env = json.load(f)
url = env['MONGO_URI']
# ============================================================== 
mongo_client = MongoClient(url)
try:
    mongo_client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
db = mongo_client['pet']
users_collection = db['users']
pets_collection = db['petfile']
questionnaire_collection = db['questionnaire']

# Google Cloud Storage 設置
service_account_json = 'lbgcs.json'
client = storage.Client.from_service_account_json(service_account_json)
bucket = client.bucket('elbgcs')

# Google Gmail SMTP 設置
gmail_user = 'petcarewy@gmail.com'
gmail_password = 'qjecpaojdaswjssg'

@app.route('/pet/send_vaccine_reminders', methods=['GET'])
def send_vaccine_reminders():  
    today = datetime.now()
    reminder_date = today

    # 查詢petfile集合中的n_va_re日期為今天的文件
    pets_due_for_vaccine = pets_collection.find({'n_va_re': reminder_date.strftime('%Y-%m-%d')})

    for pet in pets_due_for_vaccine:
        user = users_collection.find_one({'user_id': pet['user_id']})
        if user:
            send_email(user['email'], pet['p_n'], pet['n_va_re'])

    return "Vaccine reminders sent!"

def send_email(to_email, pet_name, vaccine_date):
    subject = "寵物疫苗提醒"
    body = f"親愛的寵物主人，\n\n這是一封提醒信，您的寵物 {pet_name} 預定在 {vaccine_date} 進行疫苗接種。請確保提前安排好相關事宜。\n\n此致\n毛起來健檢團隊"

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

# LINE LIFF 設置
LIFF_ID = '2005466366-WOBjGlqG'
@app.route('/qn', methods=['GET'])
def index():
    return render_template('index.html', liff_id=LIFF_ID)

@app.route('/qn/submit_form', methods=['POST'])
def submit_form():
    try:
        # 轉換為字典並保留所有值
        data = request.form.to_dict(flat=False)
        #print(f"Received form data: {data}")
        user_id = data.get('user_id', [None])[0]
        user_email = data.get('user_email', [None])[0]
        form_data = {key: value if len(value) > 1 else value[0] for key, value in data.items() if key not in ['user_id', 'user_email']}
        
        if not user_id:
            print("Missing user_id")
            return jsonify({"status": "error", "message": "Missing user_id"}), 400
        
        # 合併多選字段為字符串
        for key, value in form_data.items():
            if isinstance(value, list):
                form_data[key] = ', '.join(value)

        if 'report_photos' in request.files:
            file = request.files['report_photos']
            current_time = datetime.now().strftime("%y%m%d%H%M%S")
            file_name = f"{user_id}_{current_time}.png"
            questionnaire_blob = bucket.blob(f'pet_qn/{file_name}')
            questionnaire_blob.upload_from_file(file, content_type=file.content_type)
            form_data['report_photo_url'] = questionnaire_blob.public_url
            print(f"Uploaded photo URL: {form_data['report_photo_url']}")
        
        questionnaire_data = {
            "user_id": user_id,
            "user_email": user_email,
            **form_data
        }
        questionnaire_collection.insert_one(questionnaire_data)
        print("Inserted questionnaire data into MongoDB")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing form submission: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

@app.route('/qn/login', methods=['POST'])
def login():
    try:
        access_token = request.json.get('access_token')
        if not access_token:
            return jsonify({"status": "error", "message": "Access token is required"}), 400
        
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        response = requests.get('https://api.line.me/v2/profile', headers=headers)
        if response.status_code == 200:
            profile = response.json()
            return jsonify({"status": "success", "user_id": profile['userId']}), 200
        else:
            return jsonify({"status": "error", "message": "Invalid access token"}), 400
    except Exception as e:
        print(f"Error during login: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True)

