from time import time
from vertexai.preview.generative_models import GenerativeModel, Part
import os
import json
from io import BytesIO
from PIL import Image
import hospitalmap  #導入hospitalmap.py

from flask import Flask, request, abort, redirect

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
    MessageAction,
    ReplyMessageRequest,
    TextMessage,
    MessagingApiBlob,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    FlexMessage,
    FlexContainer,
    URIAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    PostbackEvent,
    FollowEvent,
    LocationMessageContent
)

app = Flask(__name__)

# 獲取當前腳本所在的目錄
current_script_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_script_path)
#讀取 LineBOT Key json檔
json_file_path = os.path.join(current_script_dir, 'env.json')
#讀取 GCP json檔
gcp_file_path = os.path.join(current_script_dir, 'sandrakey.json')
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


def check_pet_card_count(user_id):
    # 模擬檢查資料庫邏輯
    # 示例返回 1 表示有一張健保卡
    return 1


@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    app.logger.info(f"Postback data: {data}")
    app.logger.info(f"User ID: {user_id}")
    
    if data == 'open_camera':
        pet_card_count = check_pet_card_count(user_id)
        app.logger.info(f"Pet card count: {pet_card_count}")

        if pet_card_count < 1:
            reply_text = "還未建立毛小孩健保卡，請至選單開始建立健保卡吧!"
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
            return  # 停止後續代碼的執行

        elif pet_card_count == 1:
            reply_text = "查詢到毛小孩健保卡! 請開啟相機拍下健診資料"
            camera_action = URIAction(label='開啟相機', uri='https://line.me/R/nv/camera/')
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(text=reply_text),
                        TextMessage(text='點擊下方按鈕開啟相機', quick_reply=QuickReply(items=[
                            QuickReplyItem(action=camera_action)
                        ]))
                    ]
                )
            )
            return  # 停止後續代碼的執行


        else:  #設定成quick_reply，選擇哪一隻
            reply_text = "查詢到您有多隻寶貝，請按健保卡本中選擇要為哪一隻毛小孩建立"
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )



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
                            "max_output_tokens": 1000,
                            "temperature": 0,
                            "top_k": 1,  # 限制候選 tokens 為機率最高的 top_k 個
                            "top_p": 0.75  # 限制候選 tokens 為加總機率 (從機率機率開始) 達到 top_p 的 tokens
                            }
		#提示詞也可不設
        prompt='圖片辨識數值，遵循規則: 1.去雜質化 2.檢驗項目換行並對齊'
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


@handler.add(MessageEvent, message=(TextMessageContent, LocationMessageContent))
def handle_map_message(event):
    hospitalmap.handle_message(event, line_bot_api)




	
if __name__ == "__main__":
    app.run(debug=True)
	



