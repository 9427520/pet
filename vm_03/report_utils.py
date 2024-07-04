import io
from PIL import Image, ImageDraw, ImageFont
from google.cloud import storage
from vertexai.preview.generative_models import GenerativeModel, Part, HarmCategory, HarmBlockThreshold

def generate_suggestions(data):
    items = data.get('items', [])
    input_text = "\n".join([f"{item['key']}: {item['value']} (範圍: {item['range']})" for item in items if item['range']])
    
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
    part = Part.from_text(prompt)
    result = model.generate_content([part], generation_config=generation_config, safety_settings=safety_settings)

    try:
        suggestions = result.text.strip()
    except ValueError as e:
        print("Error retrieving response text:", e)
        suggestions = "無法生成建議，請稍後再試。"

    return suggestions

def save_report_to_gcs(image, user_id, pet_name, report_date):
    client = storage.Client()
    bucket = client.bucket('william_001')
    folder = f'{user_id}/pet'
    blob_name = f"{folder}/{pet_name}_{report_date}.png"
    blob = bucket.blob(blob_name)

    image_byte_array = io.BytesIO()
    image.save(image_byte_array, format='PNG')
    image_byte_array.seek(0)
    blob.upload_from_file(image_byte_array, content_type='image/png')

    return blob.public_url

def create_report_image(data):
    width = 1200
    initial_height = 1400
    image = Image.new('RGB', (width, initial_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    font_path = "msjh.ttc"
    text_font = ImageFont.truetype(font_path, 20)
    label_font = ImageFont.truetype(font_path, 18)

    pet_name = data.get('pet_name', '未提供')
    report_date = data.get('report_date', '未提供')
    pet_type = data.get('pet_type', '未提供')
    pet_age = data.get('pet_age', '未提供')
    pet_breed = data.get('pet_breed', '未提供')
    pet_weight = data.get('pet_weight', '未提供')
    pet_health_issues = data.get('pet_health_issues', '未提供')
    pet_food_brand = data.get('pet_food_brand', '未提供')
    
    start_x = 50
    start_y = 50
    line_spacing = 60
    column_spacing = 450

    draw.text((start_x, start_y), f"寵物名稱: {pet_name}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y), f"報告時間: {report_date}", fill="black", font=text_font)
    draw.text((start_x, start_y + line_spacing), f"寵物種類: {pet_type}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + line_spacing), f"年齡: {pet_age}", fill="black", font=text_font)
    draw.text((start_x, start_y + 2 * line_spacing), f"品種: {pet_breed}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + 2 * line_spacing), f"體重: {pet_weight}", fill="black", font=text_font)
    draw.text((start_x, start_y + 3 * line_spacing), f"已知的健康問題: {pet_health_issues}", fill="black", font=text_font)
    draw.text((start_x + column_spacing, start_y + 3 * line_spacing), f"目前餵食的品牌: {pet_food_brand}", fill="black", font=text_font)

    items = data.get('items', [])
    total_height = 300 + 50 * len(items)
    start_y = 50 + 4 * line_spacing

    bar_height = 20
    bar_length = 300

    item_x = 50
    value_x = 350
    range_x = 550
    bar_x_start = 800
    bar_x_end = bar_x_start + bar_length

    suggestions = data.get('suggestions', '無建議')
    if not isinstance(suggestions, str):
        suggestions = '無建議'
    
    suggestion_lines = []
    for line in suggestions.split('\n'):
        while len(line) > 65:
            suggestion_lines.append(line[:65])
            line = line[65:]
        suggestion_lines.append(line)
    
    suggestion_height = 30 * len(suggestion_lines)

    total_height += suggestion_height + 100
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

        if range_:
            try:
                range_start, range_end = map(float, range_.split('-'))
                value_num = float(''.join(filter(lambda x: x.isdigit() or x == '.', value)))

                if value_num < range_start:
                    bar_color = "blue"
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill=bar_color)
                    text_bbox = draw.textbbox((0, 0), "低標", font=label_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = (bar_x_start + bar_x_end) / 2 - text_width / 2
                    text_y = start_y + (bar_height - text_height) / 2 - 2
                    draw.text((text_x, text_y), "低標", fill="black", font=label_font)
                elif value_num > range_end:
                    bar_color = "red"
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill=bar_color)
                    text_bbox = draw.textbbox((0, 0), "超標", font=label_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    text_x = (bar_x_start + bar_x_end) / 2 - text_width / 2
                    text_y = start_y + (bar_height - text_height) / 2 - 2
                    draw.text((text_x, text_y), "超標", fill="black", font=label_font)
                else:
                    draw.rectangle([bar_x_start, start_y, bar_x_end, start_y + bar_height], outline="black", fill="gray")
                    position = bar_x_start + (value_num - range_start) / (range_end - range_start) * bar_length
                    draw.rectangle([bar_x_start, start_y, position, start_y + bar_height], outline="black", fill="green")
                    draw.line([position, start_y, position, start_y + bar_height], fill="red", width=3)
            except ValueError:
                pass

        draw.text((item_x, start_y), key, fill="black", font=text_font)
        draw.text((value_x, start_y), value, fill="black", font=text_font)
        draw.text((range_x, start_y), f"(範圍: {range_})" if range_ else "", fill="black", font=text_font)
        start_y += 40

    draw.text((50, start_y + 40), "AI健康建議及注意事項:", fill="black", font=text_font)

    current_y = start_y + 80
    for line in suggestion_lines:
        draw.text((50, current_y), line, fill="black", font=label_font)
        current_y += 30

    return image
