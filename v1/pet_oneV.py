# 第一版本

import os
import io
import json
import uuid
from google.cloud import vision
from PIL import Image, ImageEnhance
import numpy as np
from vertexai.preview.generative_models import GenerativeModel, Part
from time import time
from flask import Flask, request, abort, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, MessagingApiBlob
from collections import OrderedDict

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
CORS(app)  # 允许跨域请求
socketio = SocketIO(app, cors_allowed_origins="*")

# 设置当前目录为脚本所在目录
current_script_dir = os.getcwd()

# 读取 LineBOT Key json文件
json_file_path = os.path.join(current_script_dir, 'env.json')
# 读取 GCP json文件
gcp_file_path = os.path.join(current_script_dir, 'lbgcs.json')
# 设置 Google Cloud 认证
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_file_path

# LineBOT 环境配置文件
with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])

with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)
    line_bot_blob_api = MessagingApiBlob(api_client)

# 用于存储数据的全局变量
global_data = []

@app.route("/api/data", methods=['GET'])
def get_data():
    return jsonify(global_data)

@app.route("/api/update", methods=['POST'])
def update_data():
    global global_data
    data = request.json
    global_data = data
    return jsonify({"status": "success", "data": global_data})

@app.route("/callback", methods=['POST'])
def line_callback():
    # 获取 X-Line-Signature 标头值
    signature = request.headers['X-Line-Signature']

    # 将请求正文作为文本获取
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 处理 webhook 正文
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

def detect_text_orientation(image_data):
    """检测文件中的文本并返回旋转角度。"""
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_data)
    response = client.document_text_detection(image=image)
    document = response.full_text_annotation

    # 假设第一个块包含主要文本方向
    vertices = document.pages[0].blocks[0].bounding_box.vertices
    angle = get_rotation_angle(vertices)
    return angle

def get_rotation_angle(vertices):
    """根据边界框顶点计算旋转角度。"""
    dx = vertices[1].x - vertices[0].x
    dy = vertices[1].y - vertices[0].y
    angle = np.degrees(np.arctan2(dy, dx))
    return angle

def rotate_crop_and_enlarge_image(image_data, angle, scale_factor=6):
    """旋转、裁剪和放大图像。"""
    image = Image.open(io.BytesIO(image_data))
    rotated_image = image.rotate(-angle, expand=True)

    width, height = rotated_image.size
    left = 0
    top = 0
    right = width // 2
    bottom = height

    cropped_image = rotated_image.crop((left, top, right, bottom))
    
    # 放大图片
    new_size = (int(cropped_image.width * scale_factor), int(cropped_image.height * scale_factor))
    enlarged_image = cropped_image.resize(new_size, Image.LANCZOS)
    
    # 增强图像
    enhanced_image = enhance_image(enlarged_image)

    return enhanced_image

def enhance_image(image):
    """通过增加锐度、对比度和亮度来增强图像。"""
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)  # 增加锐度

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.8)  # 增加对比度

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.4)  # 增加亮度

    return image

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        image_data = message_content  # 直接使用message_content，因为它是一个bytes对象

        angle = detect_text_orientation(image_data)
        processed_image = rotate_crop_and_enlarge_image(image_data, angle)

        # 保存到内存中的字节数据
        image_byte_array = io.BytesIO()
        processed_image.save(image_byte_array, format='JPEG')
        image_bytes = image_byte_array.getvalue()

        model = GenerativeModel("gemini-1.5-pro-preview-0409")  # 模型名称可能会有所不同
        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0,
            "top_k": 1,  # 限制候选 tokens 为机率最高的 top_k 个
            "top_p": 0.75  # 限制候选 tokens 为加总机率 (从机率机率开始) 达到 top_p 的 tokens
        }

        prompt = "請辨識並列出圖片中的數據項目及其值，格式為“項目: 值”。避免返回範圍值。"
        data = Part.from_data(data=image_bytes, mime_type='image/jpeg')

        start = time()

        r = model.generate_content(
            [prompt, data],
            generation_config=generation_config
        )

        print(f'{time()-start:.3f} 秒经过')
        print(r)
        
        try:
            result_text = r.text.strip()
        except ValueError as e:
            print("Error retrieving response text:", e)
            result_text = "生成内容被安全过滤器阻止。"

        result_dict = OrderedDict()
        for line in result_text.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                if '-' not in value:
                    result_dict[key.strip()] = value.strip()

        global global_data
        global_data = [{"key": k, "value": v} for k, v in result_dict.items()]

        socketio.emit('new_data', global_data)

        liff_url = "https://liff.line.me/2005466366-9q10LQbL"

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"數據處理完成，請點擊以下連結查看和修改數據：\n{liff_url}")]
            )
        )

if __name__ == "__main__":
    #app.run()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
