import os
import json
import googlemaps
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
    MessagingApiBlob,
    MessageAction,
    ReplyMessageRequest,
    TextMessage,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    FlexMessage,
    FlexContainer
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

# Configuration for Line Bot
current_script_path = os.path.abspath(__file__)
current_script_dir = os.path.dirname(current_script_path)
json_file_path = os.path.join(current_script_dir, 'env.json')
gcp_file_path = os.path.join(current_script_dir, 'sandrakey.json')
flex_template_path = os.path.join(current_script_dir, 'hospitalmap.json')

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = gcp_file_path

with open(json_file_path, 'r') as f:
    env = json.load(f)
configuration = Configuration(access_token=env['CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(env['CHANNEL_SECRET'])

# Initialize LineBotApi and MessagingApi
with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)
    messaging_blob_api = MessagingApiBlob(api_client)

gmaps = googlemaps.Client(key="AIzaSyA-bNOE6HN2ySEMwK9dNgvgiQHUKBa3Lmc")

def pet_hospital(user_location):
    places = gmaps.places_nearby(
        location=user_location,
        radius=5000,  # 搜尋範圍
        keyword="24小時寵物診所",
        language="zh-TW"
    )

    places = places.get("results", [])

    if not places:
        return []

    results = []
    for place in places[:3]:  # 取前五間近的醫院
        place_id = place["place_id"]
        place_location = place["geometry"]["location"]
        place_address = place["vicinity"]

        details = gmaps.place(
            place_id=place_id,
            fields=["name", "formatted_phone_number", "opening_hours", "formatted_address", "photo", "current_opening_hours"],
            language="zh-TW"
        )

        result = details.get("result", {})
        hospital_name = result.get("name", "未提供名稱")
        hospital_phone = result.get("formatted_phone_number", "未提供電話號碼")
        hospital_address = result.get("formatted_address", "未提供地址")
        hospital_hours = result.get("opening_hours", {}).get("weekday_text", ["未提供營業時間"])
        photo_reference = result.get("photos", [{}])[0].get("photo_reference", "")
        is_open_now = result.get("opening_hours", {}).get("open_now", False)
        

        # 計算距離
        distance_result = gmaps.distance_matrix(user_location, hospital_address)
        distance_text = distance_result['rows'][0]['elements'][0]['distance']['text']

        results.append({
            "name": hospital_name,
            "phone": hospital_phone,
            "address": hospital_address,
            "hours": hospital_hours,
            "photo_reference": photo_reference,
            "place_id": place_id,
            "distance": distance_text,
        })



    return results

def create_flex_message(hospitals):
    with open(flex_template_path, 'r', encoding='utf-8') as f:
        flex_template = json.load(f)

    bubbles = []
    for hospital in hospitals:
        bubble = json.loads(json.dumps(flex_template["contents"][0]))  # 深拷贝模板
        bubble["body"]["contents"][0]["text"] = hospital["name"]
        bubble["body"]["contents"][1]["contents"][0]["text"] = "距離: " + hospital["distance"]
        bubble["body"]["contents"][2]["contents"][0]["text"] = hospital["address"]
        bubble["body"]["contents"][3]["contents"][0]["text"] = "\n".join(hospital["hours"])
        bubble["body"]["contents"][4]["contents"][0]["text"] = "電話: " + hospital["phone"]

        # Google map連結
        bubble["footer"]["contents"][0]["action"]["uri"] = f"https://www.google.com/maps/place/?q=place_id:{hospital['place_id']}"

        

        # 加入照片
        if hospital["photo_reference"]:
            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={hospital['photo_reference']}&key=AIzaSyA-bNOE6HN2ySEMwK9dNgvgiQHUKBa3Lmc"
            bubble["hero"]["url"] = photo_url


        bubbles.append(bubble)

    flex_message = {
        "type": "carousel",
        "contents": bubbles
    }

    flex_message_str = json.dumps(flex_message)  # 轉成json字串

    return FlexMessage(alt_text="附近的24小時營業寵物診所", contents=FlexContainer.from_json(flex_message_str))

def handle_hospital_search(event, user_location, reply_token, line_bot_api):
    hospitals = pet_hospital(user_location)
    if hospitals:
        flex_message = create_flex_message(hospitals)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[flex_message]
            )
        )
    else:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="附近沒有找到24小時營業的寵物診所。")]
            )
        )

def handle_message(event, line_bot_api):
    if isinstance(event.message, LocationMessageContent):
        user_location = (event.message.latitude, event.message.longitude)
        handle_hospital_search(event, user_location, event.reply_token, line_bot_api)
    elif isinstance(event.message, TextMessageContent):
        user_message = event.message.text.strip()
        if user_message == "尋找24小時寵物診所" or user_message == "尋找24小時寵物醫院":
            user_location = (24.98764615296507, 121.5459202780557)  # 範例的地標
            handle_hospital_search(event, user_location, event.reply_token, line_bot_api)



