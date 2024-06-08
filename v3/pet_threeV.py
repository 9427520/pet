import os
import io
import json
from google.cloud import vision
from PIL import Image, ImageEnhance, ExifTags, ImageDraw, ImageFont
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
CORS(app)  # 允許跨域請求
socketio = SocketIO(app, cors_allowed_origins="*")

# 設置當前目錄為腳本所在目錄
current_script_dir = os.getcwd()

# 讀取 LineBOT Key json文件
json_file_path = os.path.join(current_script_dir, 'weilinebot.json')
# 讀取 GCP json文件
gcp_file_path = os.path.join(current_script_dir, 'williamcloud.json')
# 設置 Google Cloud 認證
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_file_path

# LineBOT 環境配置文件
with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])

with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)
    line_bot_blob_api = MessagingApiBlob(api_client)

# 用於存儲數據的全局變數
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

@app.route("/api/generate_suggestions", methods=['POST'])
def generate_suggestions():
    data = request.json
    items = data.get('items', [])
    input_text = "\n".join([f"{item['key']}: {item['value']} (範圍: {item['range']})" for item in items if item['range']])
    
    model = GenerativeModel("gemini-1.5-pro-preview-0409")  # 模型名稱可能會有所不同
    generation_config = {
        "max_output_tokens": 1000,
        "temperature": 0,
        "top_k": 1,  # 限制候選 tokens 為機率最高的 top_k 個
        "top_p": 0.75  # 限制候選 tokens 為加總機率 (從機率機率開始) 達到 top_p 的 tokens
    }

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }

    pet_details = f"""
    寵物名稱: {data.get('pet_name', '未提供')}
    報告時間: {data.get('report_date', '未提供')}
    寵物種類: {data.get('pet_type', '未提供')}
    年齡: {data.get('pet_age', '未提供')}
    品種: {data.get('pet_breed', '未提供')}
    體重: {data.get('pet_weight', '未提供')}
    已知的健康問題: {data.get('pet_health_issues', '未提供')}
    目前餵食的品牌: {data.get('pet_food_brand', '未提供')}
    """

    prompt = f"根據以下寵物健康檢查數據提供飲食建議和注意事項：\n{pet_details}\n{input_text}"
    print(f"Generated prompt: {prompt}")  # 添加調試輸出以檢查 prompt
    part = Part.from_text(prompt)
    result = model.generate_content([part], generation_config=generation_config, safety_settings=safety_settings)

    try:
        suggestions = result.text.strip()
    except ValueError as e:
        print("Error retrieving response text:", e)
        suggestions = "無法生成建議，請稍後再試。"

    print(f"Generated suggestions: {suggestions}")  # 添加調試輸出以檢查回應
    return jsonify({"suggestions": suggestions})

@app.route("/api/generate_report", methods=['POST'])
def generate_report():
    data = request.json

    # 先獲取建議
    suggestions_response = generate_suggestions()
    suggestions_data = suggestions_response.get_json()
    data['suggestions'] = suggestions_data.get('suggestions', '無建議')

    image = create_report_image(data)

    # 將圖像轉換為 base64 字符串
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return jsonify({"report_image": img_str})

def create_report_image(data):
    width = 1200  # 保持原圖片寬度
    initial_height = 1400
    image = Image.new('RGB', (width, initial_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 添加寵物名稱和報告時間
    font_path = "C:\\Windows\\Fonts\\msjh.ttc"  # 使用支援中文的字體
    text_font = ImageFont.truetype(font_path, 20)
    label_font = ImageFont.truetype(font_path, 18)  # 調整標籤字體大小

    pet_name = data.get('pet_name', '未提供')
    report_date = data.get('report_date', '未提供')
    pet_type = data.get('pet_type', '未提供')
    pet_age = data.get('pet_age', '未提供')
    pet_breed = data.get('pet_breed', '未提供')
    pet_weight = data.get('pet_weight', '未提供')
    pet_health_issues = data.get('pet_health_issues', '未提供')
    pet_food_brand = data.get('pet_food_brand', '未提供')
    
    # 確保齊整對齊
    start_x = 50
    start_y = 50
    line_spacing = 40
    column_spacing = 300

    draw.text((start_x, start_y), f"寵物名稱: {pet_name}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y), f"報告時間: {report_date}", fill="black", font=text_font)
    draw.text((start_x, start_y + line_spacing), f"寵物種類: {pet_type}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + line_spacing), f"年齡: {pet_age}", fill="black", font=text_font)
    draw.text((start_x, start_y + 2 * line_spacing), f"品種: {pet_breed}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + 2 * line_spacing), f"體重: {pet_weight}", fill="black", font=text_font)
    draw.text((start_x, start_y + 3 * line_spacing), f"已知的健康問題: {pet_health_issues}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + 3 * line_spacing), f"目前餵食的品牌: {pet_food_brand}", fill="black", font=text_font)

    # 計算所有內容的總高度
    items = data.get('items', [])
    total_height = 300 + 50 * len(items)
    start_y = 50 + 4 * line_spacing

    bar_height = 20
    bar_length = 300

    # 設置對齊位置
    item_x = 50
    value_x = 250
    range_x = 450
    bar_x_start = 700
    bar_x_end = bar_x_start + bar_length

    # 動態調整圖像高度
    suggestions = data.get('suggestions', '無建議')
    if not isinstance(suggestions, str):
        suggestions = '無建議'
    
    # 計算建議文本的高度
    suggestion_lines = []
    for line in suggestions.split('\n'):
        while len(line) > 65:
            suggestion_lines.append(line[:65])
            line = line[65:]
        suggestion_lines.append(line)
    
    suggestion_height = 30 * len(suggestion_lines)  # 假設每行30像素高度

    total_height += suggestion_height + 100  # 增加額外高度
    if total_height > initial_height:
        image = Image.new('RGB', (width, total_height), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.text((start_x, 50), f"寵物名稱: {pet_name}", fill="black", font=text_font)
        draw.text((start_x + column_spacing, 50), f"報告時間: {report_date}", fill="black", font=text_font)
        draw.text((start_x, 50 + line_spacing), f"寵物種類: {pet_type}", fill="black", font=text_font)
        draw.text((start_x + column_spacing, 50 + line_spacing), f"年齡: {pet_age}", fill="black", font=text_font)
        draw.text((start_x, 50 + 2 * line_spacing), f"品種: {pet_breed}", fill="black", font=text_font)
        draw.text((start_x + column_spacing, 50 + 2 * line_spacing), f"體重: {pet_weight}", fill="black", font=text_font)
        draw.text((start_x, 50 + 3 * line_spacing), f"已知的健康問題: {pet_health_issues}", fill="black", font=text_font)
        draw.text((start_x + column_spacing, 50 + 3 * line_spacing), f"目前餵食的品牌: {pet_food_brand}", fill="black", font=text_font)

    for item in items:
        key = item['key']
        value = item['value']
        range_ = item['range']

        # 畫橫條圖
        if range_:
            try:
                range_start, range_end = map(float, range_.split('-'))
                value_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', value)))  # 只保留數字和小數點

                if value_num < range_start:
                    bar_color = "blue"  # 檢查數值在範圍左邊
                    # 畫橫條圖背景
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill=bar_color)
                    # 計算文字位置並添加「低標」字樣
                    text_bbox = draw.textbbox((0, 0), "低標", font=label_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = (bar_x_start + bar_x_end) / 2 - text_width / 2
                    text_y = start_y + (bar_height - text_height) / 2 - 2  # 向上移動2像素
                    draw.text((text_x, text_y), "低標", fill="black", font=label_font)
                elif value_num > range_end:
                    bar_color = "red"  # 檢查數值在範圍右邊
                    # 畫橫條圖背景
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill=bar_color)
                    # 計算文字位置並添加「超標」字樣
                    text_bbox = draw.textbbox((0, 0), "超標", font=label_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = (bar_x_start + bar_x_end) / 2 - text_width / 2
                    text_y = start_y + (bar_height - text_height) / 2 - 2  # 向上移動2像素
                    draw.text((text_x, text_y), "超標", fill="black", font=label_font)
                else:
                    # 當檢查數值在範圍內
                    # 畫橫條圖背景
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill="gray")
                    position = bar_x_start + (value_num - range_start) / (range_end - range_start) * bar_length
                    # 畫範圍內的綠色條
                    draw.rectangle([bar_x_start, start_y, position, start_y + bar_height], outline="black", fill="green")
                    # 畫檢查數值標記
                    draw.line([position, start_y, position, start_y + bar_height], fill="red", width=3)
            except ValueError:
                # 當無法轉換數值時跳過
                pass

        # 畫文字
        draw.text((item_x, start_y), key, fill="black", font=text_font)
        draw.text((value_x, start_y), value, fill="black", font=text_font)
        draw.text((range_x, start_y), f"(範圍: {range_})" if range_ else "", fill="black", font=text_font)

        # 更新Y軸起點
        start_y += 40

    # 添加建議
    draw.text((50, start_y + 20), "健康建議及注意事項:", fill="black", font=text_font)

    # 使用多行文字繪製建議
    current_y = start_y + 60
    for line in suggestion_lines:
        draw.text((50, current_y), line, fill="black", font=label_font)
        current_y += 30  # 行距調整為30像素

    return image

@app.route("/callback", methods=['POST'])
def line_callback():
    # 獲取 X-Line-Signature 標頭值
    signature = request.headers['X-Line-Signature']

    # 將請求正文作為文本獲取
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 處理 webhook 正文
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

def enhance_image(image):
    """通過增加銳度、對比度和亮度來增強圖像。"""
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)  # 增加銳度

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.8)  # 增加對比度

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.4)  # 增加亮度

    return image

def correct_image_orientation(image):
    """根據 EXIF 數據調整圖像方向。"""
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
    """放大圖像"""
    width, height = image.size
    return image.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        message_content = line_bot_blob_api.get_message_content(message_id=event.message.id)
        image_data = message_content  # 直接使用message_content，因為它是bytes對象

        image = Image.open(io.BytesIO(image_data))

        # 校正圖像方向
        image = correct_image_orientation(image)

        # 增強圖像
        enhanced_image = enhance_image(image)

        # 放大圖像
        scaled_image = resize_image(enhanced_image, scale=3.0)  # 將圖像放大 3 倍

        # 保存到內存中的字節數據
        image_byte_array = io.BytesIO()
        scaled_image.save(image_byte_array, format='JPEG')
        image_bytes = image_byte_array.getvalue()

        model = GenerativeModel("gemini-1.5-pro-preview-0409")  # 模型名稱可能會有所不同
        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0,
            "top_k": 1,  # 限制候選 tokens 為機率最高的 top_k 個
            "top_p": 0.75  # 限制候選 tokens 為加總機率 (從機率機率開始) 達到 top_p 的 tokens
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

        print(f'{time()-start:.3f} 秒經過')
        print(r)

        try:
            result_text = r.text.strip()
        except ValueError as e:
            print("Error retrieving response text:", e)
            result_text = "生成內容被安全過濾器阻止。"

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
