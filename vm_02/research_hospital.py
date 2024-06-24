# research_hospital.py
import googlemaps
import json
import os
from linebot.v3.messaging import FlexMessage, FlexContainer

current_script_dir = os.path.dirname(os.path.abspath(__file__))
flex_template_path = os.path.join(current_script_dir, 'hospitalmap.json')

gmaps = googlemaps.Client(key="AIzaSyA-bNOE6HN2ySEMwK9dNgvgiQHUKBa3Lmc")


def pet_hospital(user_location):
    places = gmaps.places_nearby(
        location=user_location,
        keyword="營業中的動物醫院",
        rank_by="distance",
        language="zh-TW"
    )
    places = places.get("results", [])

    if not places:
        return []

    results = []
    for place in places: 
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

        distance_text = "N/A"  # 初始化distance_text

        # 如果醫院現在沒有營業，跳過
        if is_open_now:

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

        print(f"Checked hospital: {hospital_name}, Open now: {is_open_now}, Distance: {distance_text}")

        if len(results) >= 3:  # 如果找到三個營業中的醫院就結束
            break

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
        bubble["footer"]["contents"][1]["action"]["uri"] = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={hospital['place_id']}"

        # 加入照片
        if hospital["photo_reference"]:
            photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={hospital['photo_reference']}&key=AIzaSyA-bNOE6HN2ySEMwK9dNgvgiQHUKBa3Lmc"
            bubble["hero"]["url"] = photo_url

        bubbles.append(bubble)

    flex_message = {
        "type": "carousel",
        "contents": bubbles
    }

    flex_message_str = json.dumps(flex_message)  # 轉換為 json

    return FlexMessage(alt_text="附近營業的寵物診所", contents=FlexContainer.from_json(flex_message_str))
