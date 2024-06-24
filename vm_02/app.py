import os
import json
import io
import base64
import logging
from time import time, strftime
from vertexai.preview.generative_models import GenerativeModel, Part, HarmCategory, HarmBlockThreshold
from collections import OrderedDict
from google.cloud import storage
from datetime import datetime
from flask import Flask, request, abort, jsonify
from flask_cors import CORS
from PIL import Image
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, FlexMessage, FlexContainer, TextMessage, TemplateMessage, ButtonsTemplate, URIAction, Sender, MessagingApiBlob, QuickReply, QuickReplyItem, CameraAction, PostbackAction, ImageMessage, PushMessageRequest, ShowLoadingAnimationRequest, LocationAction
from linebot.v3.webhooks import PostbackEvent, FollowEvent, MessageEvent, TextMessageContent, ImageMessageContent, LocationMessageContent
from pymongo import MongoClient
from bubble_utils import create_carousel 
from pet_info import save_pet_info, upload_image
from image_utils import enhance_image, correct_image_orientation, resize_image
from report_utils import generate_suggestions, save_report_to_gcs, create_report_image
from history_report import get_pet_reports, create_report_bubble
from research_hospital import pet_hospital, create_flex_message
from notifydate import LineNotifyManager


app = Flask(__name__)
CORS(app)

current_script_dir = os.getcwd()
json_file_path = os.path.join(current_script_dir, 'weilinebot.json')
gcp_file_path = os.path.join(current_script_dir, 'williamcloud.json')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_file_path

with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])

with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)
    line_bot_blob_api = MessagingApiBlob(api_client)

# MongoDB setup
url = "mongodb+srv://william:williamno1@williamhandsome.ov7ufje.mongodb.net/?retryWrites=true&w=majority&appName=williamhandsome"
mongo_client = MongoClient(url)
try:
    mongo_client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

db = mongo_client['pet']
people_collection = db['users']
pets_collection = db['petfile']
data_collection = db['data_collection']

# Google Cloud Storage setup
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_file_path
storage_client = storage.Client()
bucket_name = "william_001"
bucket = storage_client.bucket(bucket_name)

REDIRECT_URI = env['NOTIFY_REDIRECT_URI']
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

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

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
        
def send_message_with_selected_pet(user_id, reply_token, message_text, additional_messages=None):
    if not isinstance(message_text, str) or not message_text:
        message_text = "系統訊息"  # 设定一个默认的消息文本
    
    selected_pet = pets_collection.find_one({"user_id": user_id, "selected": True})

    sender = None
    if selected_pet:
        sender = Sender(
            name=selected_pet.get("p_n", "Pet"),
            icon_url=selected_pet.get("image", "")
        )

    messages = []
    
    # Create the initial message with the sender info
    message = TextMessage(
        text=message_text,
        sender=sender
    )
    messages.append(message)

    # Append additional messages, each with the sender info
    if additional_messages:
        for additional_message in additional_messages:
            if isinstance(additional_message, (FlexMessage, TextMessage, TemplateMessage)):
                additional_message.sender = sender
            messages.append(additional_message)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages
            )
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    postback_data = event.postback.data
    user_id = event.source.user_id
    reply_token = event.reply_token
    liff_url2 = "https://liff.line.me/2005517118-y7Y7mPLA"


    selected_pet = pets_collection.find_one({"user_id": user_id, "selected": True})
    sender = None
    if selected_pet:
        sender = Sender(
            name=selected_pet.get("p_n", "Pet"),
            icon_url=selected_pet.get("image", "")
        )
    
    if postback_data == "毛小孩健保卡":
        pets = list(pets_collection.find({"user_id": user_id}))
        if pets:
            formatted_results = []
            for pet in pets:
                formatted_result = {
                    "p_n": pet.get("p_n"),
                    "p_g": pet.get("p_g"),
                    "p_t": pet.get("p_t"),
                    "p_v": pet.get("p_v"),
                    "p_w": pet.get("p_w"),
                    "p_b": pet.get("p_b"),
                    "p_va": pet.get("p_va"),
                    "n_va_re": pet.get("n_va_re"),
                    "image": pet.get("image"),
                    "age": pet.get("age")
                }
                formatted_results.append(formatted_result)

            welcome_message = TextMessage(
                text="請選擇一隻寵物以繼續。"
            )

            carousel = create_carousel(formatted_results)
            flex_container = FlexContainer.from_dict(carousel)
            flex_message = FlexMessage(
                alt_text="毛小孩健保卡",
                contents=flex_container
            )

            quick_reply_buttons = QuickReply(items=[
                QuickReplyItem(action=URIAction(label="新增資料", uri=liff_url2))
            ])

            flex_message.quick_reply = quick_reply_buttons

            send_message_with_selected_pet(user_id, reply_token, welcome_message.text, [flex_message])

        else:
            message = "請點擊以下連結建立健保卡：\n{}".format(liff_url2)
            send_message_with_selected_pet(user_id, reply_token, message)

    elif postback_data == "照相":
        pets = list(pets_collection.find({"user_id": user_id}))
        if not pets:
            message = "請點擊以下連結先創建寵物資料：\n{}".format(liff_url2)
            send_message_with_selected_pet(user_id, reply_token, message)
        else:
            selected_pet = pets_collection.find_one({"user_id": user_id, "selected": True})
            if not selected_pet:
                message = "請選擇寵物。"
                send_message_with_selected_pet(user_id, reply_token, message)
            else:
                quick_reply = QuickReply(items=[
                    QuickReplyItem(action=CameraAction(label="拍照"))
                ])
                message = TextMessage(text="請拍攝或上傳寵物的健康檢查報告。", sender=sender, quick_reply=quick_reply)
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    
                    loading_animation_request = ShowLoadingAnimationRequest(
                        chatId=user_id,
                        loadingSeconds=5
                    )
                    line_bot_api.show_loading_animation(loading_animation_request)
                    
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[message]
                        )
                    )
                    
    elif postback_data == "報告":
        pets = list(pets_collection.find({"user_id": user_id}))
        if not pets:
            message = "請點擊以下連結先創建寵物資料：\n{}".format(liff_url2)
            send_message_with_selected_pet(user_id, reply_token, message)
        else:
            quick_reply_items = [
                QuickReplyItem(action=PostbackAction(label=pet['p_n'], data=json.dumps({"action": "view_history", "p_n": pet['p_n']})))
                for pet in pets if get_pet_reports('william_001', user_id, pet['p_n'])
            ]
            if quick_reply_items:
                quick_reply = QuickReply(items=quick_reply_items)
                message = TextMessage(text="請選擇一隻寵物以查看其歷史報告。", sender=sender, quick_reply=quick_reply)
                with ApiClient(configuration) as api_client:
                    line_bot_api = MessagingApi(api_client)
                    
                    loading_animation_request = ShowLoadingAnimationRequest(
                        chatId=user_id,
                        loadingSeconds=5
                    )
                    line_bot_api.show_loading_animation(loading_animation_request)
                    
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[message]
                        )
                    )
            else:
                message = "目前沒有寵物報告可顯示。請先上傳健康檢查報告。"
                send_message_with_selected_pet(user_id, reply_token, message)
                                
    elif postback_data == '寵物醫院':
    # 請求使用者的位置信息
        quick_reply = QuickReply(items=[
             QuickReplyItem(action=LocationAction(label="傳送位置"))
        ])
        message = TextMessage(text="請傳送您的位置資訊，以便查找附近的寵物醫院。", sender=sender, quick_reply=quick_reply)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
                
            loading_animation_request = ShowLoadingAnimationRequest(
                chatId=user_id,
                loadingSeconds=5
            )
            line_bot_api.show_loading_animation(loading_animation_request)
                
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[message]
                )
            )

    elif postback_data == '團隊介紹':
        with ApiClient(configuration) as api_client:
            with open('team.json', encoding='utf-8') as f:
                t = f.read()
            flex_message = FlexMessage(altText='團隊介紹', contents=FlexContainer.from_json(t))
            send_message_with_selected_pet(user_id, reply_token, "這是我們的團隊介紹", [flex_message])


    else:
        data = json.loads(postback_data)
        action = data.get("action")

        if action == "view_history":
            pet_name = data.get("p_n")
            report_files = get_pet_reports('william_001', user_id, pet_name)
            if report_files:
                bubble = create_report_bubble(pet_name, report_files, user_id)
                messages = [FlexMessage(alt_text=f"{pet_name} 的歷史報告", contents=FlexContainer.from_dict(bubble))]

                quick_reply_items = [
                    QuickReplyItem(action=PostbackAction(label=pet['p_n'], data=json.dumps({"action": "view_history", "p_n": pet['p_n']})))
                    for pet in pets_collection.find({"user_id": user_id}) if get_pet_reports('william_001', user_id, pet['p_n'])
                ]
                if quick_reply_items:
                    quick_reply = QuickReply(items=quick_reply_items)
                    messages[0].quick_reply = quick_reply

                send_message_with_selected_pet(user_id, reply_token, "", messages)
            else:
                send_message_with_selected_pet(user_id, reply_token, f"目前該寵物 {pet_name} 並沒有報告。")

        elif action == 'delete_report':
            report_name = data.get('report_name')
            client = storage.Client()
            bucket_name = 'william_001'
            folder = f'{user_id}/pet'
            bucket = client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=folder)
            matching_blobs = [blob for blob in blobs if report_name in blob.name]
            if matching_blobs:
                matching_blob = matching_blobs[0]
                matching_blob.delete()

                pets = list(pets_collection.find({"user_id": user_id}))
                pet_name = data.get("p_n")
                report_files = get_pet_reports('william_001', user_id, pet_name)
                if report_files:
                    bubble = create_report_bubble(pet_name, report_files, user_id)
                    messages = [FlexMessage(alt_text=f"{pet_name} 的歷史報告", contents=FlexContainer.from_dict(bubble))]
                    
                    quick_reply_items = [
                        QuickReplyItem(action=PostbackAction(label=pet['p_n'], data=json.dumps({"action": "view_history", "p_n": pet['p_n']})))
                        for pet in pets if get_pet_reports('william_001', user_id, pet['p_n'])
                    ]
                    quick_reply = QuickReply(items=quick_reply_items)
                    messages[0].quick_reply = quick_reply
                    send_message_with_selected_pet(user_id, reply_token, f" 已成功刪除。", messages)
                else:
                    send_message_with_selected_pet(user_id, reply_token, f"已成功刪除，目前該寵物 {pet_name} 並沒有報告。")
            else:
                send_message_with_selected_pet(user_id, reply_token, "找不到指定的報告。")

        elif action == 'delete_pet':
            pet_name = data.get('p_n')
            pets_collection.delete_one({"user_id": user_id, "p_n": pet_name})

            pets = list(pets_collection.find({"user_id": user_id}))
            if pets:
                formatted_results = []
                for pet in pets:
                    formatted_result = {
                        "p_n": pet.get("p_n"),
                        "p_g": pet.get("p_g"),
                        "p_t": pet.get("p_t"),
                        "p_v": pet.get("p_v"),
                        "p_w": pet.get("p_w"),
                        "p_b": pet.get("p_b"),
                        "p_va": pet.get("p_va"),
                        "n_va_re": pet.get("n_va_re"),
                        "image": pet.get("image"),
                        "age": pet.get("age")
                    }
                    formatted_results.append(formatted_result)

                welcome_message = TextMessage(
                    text="寵物已刪除，請選擇其他寵物以繼續。"
                )

                carousel = create_carousel(formatted_results)
                flex_container = FlexContainer.from_dict(carousel)
                flex_message = FlexMessage(
                    alt_text="毛小孩健保卡",
                    contents=flex_container
                )

                quick_reply_buttons = QuickReply(items=[
                    QuickReplyItem(action=URIAction(label="新增資料", uri=liff_url2))
                ])

                flex_message.quick_reply = quick_reply_buttons

                send_message_with_selected_pet(user_id, reply_token, welcome_message.text, [flex_message])
            else:
                message = "寵物已刪除，請點擊以下連結新增寵物資料：\n{}".format(liff_url2)
                send_message_with_selected_pet(user_id, reply_token, message)

       
        else:
            pet_data = json.loads(postback_data)
            pet_image_url = pet_data.get("image", "")

            if pet_image_url:
                sender = Sender(
                    name=pet_data.get("p_n", "Pet"),
                    icon_url=pet_image_url
                )

                selected_message = TextMessage(
                    text=f"您選擇了{pet_data.get('p_n', '寵物')}!",
                    sender=sender
                )

                pets_collection.update_many(
                    {"user_id": user_id},
                    {"$set": {"selected": False}}
                )
                pets_collection.update_one(
                    {"user_id": user_id, "p_n": pet_data['p_n']},
                    {"$set": {"selected": True}}
                )

                send_message_with_selected_pet(user_id, reply_token, selected_message.text)

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    user_id = data.get('user_id')
    message_text = data.get('message_text')
    reply_token = data.get('reply_token')
    
    send_message_with_selected_pet(user_id, reply_token, message_text)
    return jsonify({'status': 'success', 'message': 'Message sent'})

@app.route('/save_pet_info', methods=['POST'])
def save_pet_info_route():
    data = request.json
    return save_pet_info(data)

@app.route('/upload_image', methods=['POST'])
def upload_image_route():
    data = request.json
    return upload_image(data)

@app.route("/api/data", methods=['GET'])
def get_data():
    user_id = request.args.get('user_id')
    print(f"Fetching data for user_id: {user_id}")
    data = data_collection.find_one({"user_id": user_id}, {"_id": 0})
    print(f"Data found: {data}")

    if data:
        return jsonify(data.get("items", []))
    else:
        print("No data found")
        return jsonify([]), 404

@app.route("/get_selected_pet", methods=['GET'])
def get_selected_pet():
    user_id = request.args.get('user_id')
    print(f"Fetching selected pet for user_id: {user_id}")
    pet = pets_collection.find_one({"user_id": user_id, "selected": True}, {"_id": 0})
    print(f"Pet found: {pet}")

    if pet:
        return jsonify(pet)
    else:
        print("No pet found")
        return jsonify({"message": "Pet not found"}), 404

@app.route("/api/update", methods=['POST'])
def update_data():
    data = request.json
    user_id = data.get('user_id')
    items = data.get('items', [])
    data_collection.update_one({"user_id": user_id}, {"$set": {"items": items}}, upsert=True)
    return jsonify({'status': 'success'})

@app.route("/api/generate_suggestions", methods=['POST'])
def generate_suggestions_route():
    data = request.get_json()
    suggestions = generate_suggestions(data)
    return jsonify({"suggestions": suggestions})

@app.route("/api/generate_report", methods=['POST'])
def generate_report_route():
    data = request.get_json()
    user_id = data.get('user_id')


    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        loading_animation_request = ShowLoadingAnimationRequest(
            chatId=user_id,
            loadingSeconds=15
        )
        line_bot_api.show_loading_animation(loading_animation_request)
                

    # 生成報告
    suggestions = generate_suggestions(data)
    data['suggestions'] = suggestions
    image = create_report_image(data)
    image_url = save_report_to_gcs(image, user_id, data['pet_name'], data['report_date'])

    # 推送圖片訊息
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        image_message = ImageMessage(
            original_content_url=image_url,
            preview_image_url=image_url  # 可以使用相同的URL作為預覽圖像
        )
        push_image_message_request = PushMessageRequest(
            to=user_id,
            messages=[image_message]
        )
        line_bot_api.push_message(push_image_message_request)

    return jsonify({"report_image_url": image_url})

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    with ApiClient(configuration) as api_client:
    
        loading_animation_request = ShowLoadingAnimationRequest(
            chatId=event.source.user_id,
            loadingSeconds=20
        )
        line_bot_api.show_loading_animation(loading_animation_request)
        
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        image_data = message_content

        image = Image.open(io.BytesIO(image_data))

        image = correct_image_orientation(image)

        enhanced_image = enhance_image(image)
        
        scaled_image = resize_image(enhanced_image, scale=3.0)

        image_byte_array = io.BytesIO()
        scaled_image.save(image_byte_array, format='JPEG')
        image_bytes = image_byte_array.getvalue()

        model = GenerativeModel("gemini-1.5-pro-preview-0409")
        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0,
            "top_k": 1,
            "top_p": 0.75
        }

        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

        prompt = "請辨識並列出圖片中的數據項目、數值及其範圍值，格式為“項目: 數值 (範圍值)”，如果範圍值為空，請留空。"
        data = Part.from_data(data=image_bytes, mime_type='image/jpeg')

        start = time()
        r = model.generate_content([prompt, data], generation_config=generation_config, safety_settings=safety_settings)
        print(f'{time()-start:.3f} 秒經過')
        print(r)

        try:
            result_text = r.text.strip()
        except ValueError as e:
            print("Error retrieving response text:", e)
            result_text = "生成內容被安全過濾器阻止。"

        result_dict = OrderedDict()
        for line in result_text.splitlines():
            if (': ' in line):
                key, value_range = line.split(': ', 1)
                if ('(' in value_range and ')' in value_range):
                    value, range_ = value_range.split('(', 1)
                    range_ = range_.strip(')')
                else:
                    value = value_range
                    range_ = ''
                result_dict[key.strip()] = (value.strip(), range_)

        user_id = event.source.user_id
        data_to_save = [{"key": k, "value": v[0], "range": v[1]} for k, v in result_dict.items()]

        data_collection.delete_many({"user_id": user_id})
        data_collection.insert_one({"user_id": user_id, "items": data_to_save})

        liff_url1 = "https://liff.line.me/2005517118-y5JKr3xg"
        send_message_with_selected_pet(user_id, event.reply_token, f"數據處理完成，請點擊以下連結查看和修改數據：\n{liff_url1}")

@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    user_location = (event.message.latitude, event.message.longitude)

    # 查找附近的動物醫院
    hospitals = pet_hospital(user_location)
    if hospitals:
        loading_animation_request = ShowLoadingAnimationRequest(
            chatId=user_id,
            loadingSeconds=5
        )
        line_bot_api.show_loading_animation(loading_animation_request)
        
        flex_message = create_flex_message(hospitals)
        send_message_with_selected_pet(user_id, reply_token, "以下是附近的寵物醫院資訊：", [flex_message])
    else:
        send_message_with_selected_pet(user_id, reply_token, "找不到附近的寵物醫院。")

if __name__ == "__main__":
    line_notify_manager.schedule_notifications()
    app.run()
