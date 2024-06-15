import os
from google.cloud import storage
from datetime import datetime

def upload_image_to_gcs(file, user_id, pid):
    # Set your Google Cloud Storage credentials and bucket name
    # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path/to/your/credentials.json"
    # bucket_name = "your-bucket-name"
    
    # Create a storage client
    client = storage.Client.from_service_account_json('lbgcs.json')
    bucket = client.bucket('elbgcs')
    current_time = datetime.now().strftime("%y%m%d%H%M%S")
    filename = f"pet_profile/{user_id}_{pid}.jpg"
    blob = bucket.blob(filename)

    # Upload the file to GCS
    # blob.upload_from_file(file, content_type=file.content_type)
    blob.upload_from_file(file, content_type='image/jpeg')  # 手動設置 content_type
    
    
    # Make the blob publicly viewable
    blob.make_public()
    
    # Return the public URL
    return blob.public_url
