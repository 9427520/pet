import os
import io
import json
from google.cloud import vision
from PIL import Image, ImageEnhance, ExifTags, ImageDraw, ImageFont
import numpy as np
from vertexai.preview.generative_models import GenerativeModel, Part, HarmCategory, HarmBlockThreshold
from time import time
from flask import Flask, request, abort, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, MessagingApiBlob
from linebot.v3.webhooks import MessageEvent, ImageMessageContent
from collections import OrderedDict
import base64

app = Flask(__name__)
CORS(app)  # 允许跨域请求
socketio = SocketIO(app, cors_allowed_origins="*")

# 设置当前目录为脚本所在目录
current_script_dir = os.getcwd()

# 读取 LineBOT Key json文件
json_file_path = os.path.join(current_script_dir, 'weilinebot.json')
# 读取 GCP json文件
gcp_file_path = os.path.join(current_script_dir, 'williamcloud.json')
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

@app.route("/api/generate_report", methods=['POST'])
def generate_report():
    data = request.json
    image = create_report_image(data)

    # 将图像转换为 base64 字符串
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return jsonify({"report_image": img_str})

def create_report_image(data):
    width, height = 800, 1200  # 圖片的寬度和高度
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 添加標題
    font_path = "C:\\Windows\\Fonts\\msjh.ttc"  # 使用支援中文的字體
    font = ImageFont.truetype(font_path, 40)
    draw.text((width / 2 - 100, 50), "寵物健檢報告", fill="black", font=font)

    # 添加表格數據
    font = ImageFont.truetype(font_path, 20)
    start_y = 150
    for item in data:
        if item['range']:  # 如果範圍不為空
            text = f"{item['key']}: {item['value']} (範圍: {item['range']})"
        else:  # 如果範圍為空
            text = f"{item['key']}: {item['value']}"
        draw.text((50, start_y), text, fill="black", font=font)
        start_y += 30

    return image

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

def enhance_image(image):
    """通过增加锐度、对比度和亮度来增强图像。"""
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)  # 增加锐度

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.8)  # 增加对比度

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.4)  # 增加亮度

    return image

def correct_image_orientation(image):
    """根据 EXIF 数据调整图像方向。"""
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break

        exif = dict(image._getexif().items())

        if exif[orientation] == 3:
            image = image.rotate(180, expand=True)
        elif exif[orientation] == 6:
            image = image.rotate(270, expand=True)
        elif exif[orientation] == 8:
            image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        # cases: image don't have getexif
        pass

    return image

def resize_image(image, scale):
    """放大图像"""
    width, height = image.size
    return image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        image_data = message_content  # 直接使用message_content，因为它是一个bytes对象

        image = Image.open(io.BytesIO(image_data))

        # 校正图像方向
        image = correct_image_orientation(image)

        # 增强图像
        enhanced_image = enhance_image(image)

        # 放大图像
        scaled_image = resize_image(enhanced_image, scale=3.0)  # 将图像放大 3 倍

        # 保存到内存中的字节数据
        image_byte_array = io.BytesIO()
        scaled_image.save(image_byte_array, format='JPEG')
        image_bytes = image_byte_array.getvalue()

        model = GenerativeModel("gemini-1.5-pro-preview-0409")  # 模型名称可能会有所不同
        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0,
            "top_k": 1,  # 限制候选 tokens 为机率最高的 top_k 个
            "top_p": 0.75  # 限制候选 tokens 为加总机率 (从机率机率开始) 达到 top_p 的 tokens
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

        r = model.generate_content(
            [prompt, data],
            generation_config=generation_config,
            safety_settings=safety_settings
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
                key, value_range = line.split(':', 1)
                if '(' in value_range and ')' in value_range:
                    value, range_ = value_range.split('(', 1)
                    range_ = range_.strip(')')
                else:
                    value = value_range
                    range_ = ''
                result_dict[key.strip()] = (value.strip(), range_)

        global global_data
        global_data = [{"key": k, "value": v[0], "range": v[1]} for k, v in result_dict.items()]

        socketio.emit('new_data', global_data)

        liff_url = "https://liff.line.me/2005517118-y5JKr3xg"

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"數據處理完成，請點擊以下連結查看和修改數據：\n{liff_url}")]
            )
        )

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
