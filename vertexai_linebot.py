from time import time
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
    QuickReplyItem
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
json_file_path = os.path.join(current_script_dir, 'env.json')
#讀取 GCP json檔
gcp_file_path = os.path.join(current_script_dir, 'lbgcs.json')
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
	
if __name__ == "__main__":
    app.run()	
	