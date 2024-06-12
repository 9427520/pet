
from copy import deepcopy
from time import time
from vertexai.generative_models import GenerativeModel
import vertexai.preview.generative_models as generative_models
from vertexai.preview.generative_models import GenerativeModel, Part
import os
import json
from io import BytesIO
from PIL import Image

from flask import Flask, request, abort

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    MessagingApiBlob,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    FlexMessage,
    FlexContainer,
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    PostbackEvent
)

app = Flask(__name__)

# 獲取當前腳本所在的目錄
current_script_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_script_path)
#讀取 LineBOT Key json檔
json_file_path = os.path.join(current_script_dir, 'reminder.json')
#讀取 GCP json檔
gcp_file_path = os.path.join(current_script_dir, 'classtest_cloud_key.json')
# gcloud auth application-default login
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_file_path
# LineBOT ENV Config file
with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])



with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)
    line_bot_blob_api = MessagingApiBlob(api_client)


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'



@handler.add(MessageEvent, message=ImageMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        model = GenerativeModel("gemini-1.5-pro")  # model name
        image_data = BytesIO(message_content)
        image = Image.open(image_data)
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()
        data_part = Part.from_data(data=image_bytes, mime_type='image/jpeg')
        generation_config = {
                            "max_output_tokens": 700,
                            "temperature": 0,
                            "top_k": 1,  # 限制候選 tokens 為機率最高的 top_k 個
                            "top_p": 0.75  # 限制候選 tokens 為加總機率 (從機率機率開始) 達到 top_p 的 tokens
                            }
        
    #     safety_settings = {
    #     generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
    #     generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
    #     generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE,
    #     generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
    # }
		#提示詞也可不設
        prompt='這是一份寵物健檢報告,需要圖片辨識數值，遵循規則: 1.去雜質化 2.檢驗項目換行並對齊 3.只需要回傳檢驗項目以及接在後方的第一個檢驗結果,中間以|分隔 '
        r = model.generate_content(
                                    [prompt, data_part],
                                    generation_config=generation_config
                                    )



        msg = r.text.strip()
		#print出結果可以看有無正確輸出	
        # print(r)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=msg)]
        )
    )
        
index = ['寵物1', '寵物2', '寵物3', '寵物4', '寵物5']
users = {i: {"userid": ""} for i in index}  # 這裡需要您填入實際的用戶數據

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    text = event.message.text
    user_id = event.source.user_id

    if text == "健保卡":
        items = [
            QuickReplyItem(action=MessageAction(label=str(i), text=str(i)))
            for i in range(1, 6)
        ]
        quick_reply = QuickReply(items=items)
        msg = TextMessage(text="你有幾隻毛小孩呢?", quick_reply=quick_reply)
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[msg]))
    elif text.isdigit() and 1 <= int(text) <= 5:
        count = int(text)
        if count == 1:
            bubble = create_bubble(1)
            message = FlexMessage(alt_text=f'毛小孩1', contents=FlexContainer.from_dict(bubble))
        else:
            carousel_data = ncard(count)
            carousel = FlexContainer.from_dict(carousel_data)
            message = FlexMessage(alt_text='毛小孩們', contents=carousel)

        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[message]))
        # Initialize user's pet data
        user_data = load_user_data()
        user_data[user_id] = [{"name": "", "gender": "", "breed": "", "birth_date": "", "vaccine_date": ""} for _ in range(count)]
        save_user_data(user_data)
    elif text.startswith("編輯"):
        _, field, value = text.split(':', 2)
        user_data = load_user_data().get(user_id, [])
        for pet in user_data:
            pet[field] = value
        save_user_data({user_id: user_data})
        msg = TextMessage(text=f"{field} 已更新為 {value}。請點擊確認存檔。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[msg]))
    else:
        msg = TextMessage(text="請選擇有效選項或輸入'建立健保卡'來開始。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[msg]))

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    if data == "action=edit":
        # 顯示可編輯的 Bubble 給使用者
        with open('card_edit.json', encoding='utf-8') as f:
            bubble = json.load(f)
        message = FlexMessage(alt_text='編輯資料', contents=FlexContainer.from_dict(bubble))
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[message]))
    elif data == "action=confirm":
        # 獲取使用者修改的資訊並更新 user_data.json
        user_id = event.source.user_id
        user_data = load_user_data().get(user_id, [])
        save_user_data({user_id: user_data})
        msg = TextMessage(text="資料已保存。")
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[msg]))

def create_bubble(index):
    with open('card_edit.json', encoding='utf-8') as f:
        bubble = json.load(f)
    bubble['body']['contents'][0]['contents'][1]['contents'][1]['text'] = f'寵物{index}'
    bubble['body']['contents'][0]['contents'][0]['contents'][0]['text'] = ""
    return bubble

def ncard(n):
    with open('card_edit.json', encoding='utf-8') as f:
        j = json.load(f)
    print("Card structure:", json.dumps(j, indent=2, ensure_ascii=False))  # Debugging line
    d = {"type": "carousel", "contents": []}
    for i in range(n):
        x = deepcopy(j)
        if len(x['body']['contents'][0]['contents']) > 1 and len(x['body']['contents'][0]['contents'][1]['contents']) > 1:
            x['body']['contents'][0]['contents'][1]['contents'][1]['text'] = index[i]  # user名字
            x['body']['contents'][0]['contents'][1]['contents'][0]['text'] = users[index[i]]['userid']
            d['contents'].append(x)
        else:
            print(f"Index {i} out of range in card structure")  # Debugging line
    return d

def save_user_data(data):
    with open("user_data.json", "w") as f:
        json.dump(data, f)

def load_user_data():
    try:
        with open("user_data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


	
if __name__ == "__main__":
    app.run()	
	