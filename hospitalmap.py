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
        keyword = "動物醫院",
        rank_by = "distance",
        language="zh-TW"
    )
    places = places.get("results", [])

    if not places:
        return []

    results = []
    for place in places[:3]:  #取前三間近的醫院
        place_id = place["place_id"]
        place_location = place["geometry"]["location"]
        place_address = place["vicinity"]

        details = gmaps.place(
            place_id=place_id,
            fields=["name", "formatted_phone_number", "opening_hours", "formatted_address", "photo", "current_opening_hours", "rating"],
            language="zh-TW"
        )

        result = details.get("result", {})
        hospital_name = result.get("name", "未提供名稱")
        hospital_phone = result.get("formatted_phone_number", "未提供電話號碼")
        hospital_address = result.get("formatted_address", "未提供地址")
        hospital_hours = result.get("opening_hours", {}).get("weekday_text", ["未提供營業時間"])
        photo_reference = result.get("photos", [{}])[0].get("photo_reference", "")
        is_open_now = result.get("opening_hours", {}).get("open_now", False)
        hospital_rating = result.get("rating", 0)
        
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
            "rating": hospital_rating
        })

    return results


def pet_hotel(user_location):
    places = gmaps.places_nearby(
        location=user_location,
        keyword="寵物住宿",
        rank_by="distance",
        language="zh-TW"
    )

    places = places.get("results", [])

    if not places:
        return []

    results = []
    for place in places[:3]:  # 取前三間近的住宿
        place_id = place["place_id"]
        place_address = place["vicinity"]

        details = gmaps.place(
            place_id=place_id,
            fields=["name", "formatted_phone_number", "opening_hours", "formatted_address", "photo", "rating"],
            language="zh-TW"
        )

        result = details.get("result", {})
        hotel_name = result.get("name", "未提供名稱")
        hotel_phone = result.get("formatted_phone_number", "未提供電話號碼")
        hotel_address = result.get("formatted_address", place_address)
        hotel_hours = result.get("opening_hours", {}).get("weekday_text", ["未提供營業時間"])
        photo_reference = result.get("photos", [{}])[0].get("photo_reference", "")
        hotel_rating = result.get("rating", 0)
        
        try:
            distance_result = gmaps.distance_matrix(user_location, hotel_address)
            distance_text = distance_result['rows'][0]['elements'][0]['distance']['text']
        except Exception as e:
            print(f"Error calculating distance: {e}")
            distance_text = "距離未知"

        results.append({
            "name": hotel_name,
            "phone": hotel_phone,
            "address": hotel_address,
            "hours": hotel_hours,
            "photo_reference": photo_reference,
            "place_id": place_id,
            "distance": distance_text,
            "rating": hotel_rating
        })

    return results


def create_flex_message(hospitals):
    with open(flex_template_path, 'r', encoding='utf-8') as f:
        flex_template = json.load(f)

    bubbles = []
    for hospital in hospitals:
        bubble = json.loads(json.dumps(flex_template["contents"][0]))  # 深拷贝模板
        bubble["body"]["contents"][0]["text"] = hospital["name"]

        # 生成星星評價
        stars = ""
        rating = int(hospital['rating'])
        for i in range(5):
            if i < rating:
                stars += "⭐"
            

        bubble["body"]["contents"][1]["contents"][0]["text"] = f"{stars} {hospital['rating']}"
        bubble["body"]["contents"][2]["contents"][0]["text"] = "距離: " + hospital["distance"]
        bubble["body"]["contents"][3]["contents"][0]["text"] = hospital["address"]
        

        formatted_hours = "\n".join(hospital["hours"])
        bubble["body"]["contents"][4]["contents"][0]["text"] = formatted_hours

        if len(hospital["hours"]) > 5:
            bubble["body"]["contents"][4]["contents"][0]["size"] = "xs"  # 缩小字体


        # 確保電話格式
        phone_number = hospital["phone"]
        if phone_number == "未提供電話號碼":
            phone_number = "0000000000"
        else:
            # 移除空格和破折號
            phone_number = phone_number.replace(" ", "").replace("-", "")

        # 電話、 Google map連結
        bubble["footer"]["contents"][0]["action"]["type"] = "uri"
        bubble["footer"]["contents"][0]["action"]["uri"] = f"tel:{phone_number}"
        bubble["footer"]["contents"][1]["action"]["uri"] = f"https://www.google.com/maps/place/?q=place_id:{hospital['place_id']}"
        

        # 加入照片
        if hospital["photo_reference"]:
            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={hospital['photo_reference']}&key=AIzaSyA-bNOE6HN2ySEMwK9dNgvgiQHUKBa3Lmc"
            bubble["hero"]["url"] = photo_url


        bubbles.append(bubble)

    flex_message = {
        "type": "carousel",
        "contents": bubbles
    }

    flex_message_str = json.dumps(flex_message)  #轉換為json

    return FlexMessage(alt_text="附近營業的寵物診所", contents=FlexContainer.from_json(flex_message_str))


#暫定的寵物健保卡資料數
def check_pet_card_count(user_id):
        return 1


#根據辨識健保卡開啟相機
def postback_idcard_camera_event(event):
    try:
        data = event.postback.data
        user_id = event.source.user_id
        app.logger.info(f"Postback data: {data}")
        app.logger.info(f"User ID: {user_id}")

        if data == 'open_camera':
            pet_card_count = check_pet_card_count(user_id)
            app.logger.info(f"Pet card count: {pet_card_count}")

            if pet_card_count < 1:
                reply_text = "還未建立毛小孩健保卡，請至選單開始建立健保卡吧!"
                app.logger.info(f"Replying with message: {reply_text}")
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
                return

            elif pet_card_count == 1:
                reply_text = "查詢到毛小孩健保卡! 請開啟相機拍下健診資料"
                camera_action = URIAction(label='開啟相機', uri='https://line.me/R/nv/camera/')
                app.logger.info(f"Replying with camera action message: {reply_text}")
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
                return

            else:
                reply_text = "查詢到您有多隻寶貝，請按健保卡本中選擇要為哪一隻毛小孩建立"
                app.logger.info(f"Replying with multiple pets message: {reply_text}")
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
    except Exception as e:
        app.logger.error(f"Error in postback_idcard_camera_event: {e}")


