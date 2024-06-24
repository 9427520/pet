import os
import json
import base64
import logging
from flask import jsonify
from pymongo import MongoClient
from google.cloud import storage

# MongoDB setup
url = "mongodb+srv://william:williamno1@williamhandsome.ov7ufje.mongodb.net/?retryWrites=true&w=majority&appName=williamhandsome"
mongo_client = MongoClient(url)
db = mongo_client['pet']
pets_collection = db['petfile']

# Google Cloud Storage setup
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'williamcloud.json'
storage_client = storage.Client()
bucket_name = "william_001"
bucket = storage_client.bucket(bucket_name)

def save_pet_info(data):
    try:
        user_id = data.get('user_id')
        pet_name = data.get('p_n')

        if not user_id or not pet_name:
            return jsonify({'status': 'fail', 'message': 'Missing user_id or pet name'}), 400

        existing_pet = pets_collection.find_one({"user_id": user_id, "p_n": pet_name})

        if existing_pet:
            pets_collection.update_one(
                {"user_id": user_id, "p_n": pet_name},
                {"$set": data}
            )
            return jsonify({'status': 'success', 'message': 'Pet information updated'})
        else:
            pets_collection.insert_one(data)
            return jsonify({'status': 'success', 'message': 'Pet information saved'})

    except Exception as e:
        print(e)
        return jsonify({'status': 'fail', 'message': str(e)})

def upload_image(data):
    try:
        if 'image' not in data:
            raise ValueError("No image data provided")

        image_data = data['image']
        if image_data.startswith('data:image/'):
            header, encoded = image_data.split(',', 1)
            file_extension = header.split('/')[1].split(';')[0]
        else:
            raise ValueError("Invalid image data format")

        decoded_image = base64.b64decode(encoded)
        blob_name = f"pet_info/{os.urandom(16).hex()}.{file_extension}"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(decoded_image, content_type=f"image/{file_extension}")
        image_url = blob.public_url

        logging.info(f"Image uploaded to: {image_url}")
        return jsonify({"status": "success", "url": image_url}), 200
    except Exception as e:
        logging.error(f"Error uploading image: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
