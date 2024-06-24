import json
from google.cloud import storage
import os
from copy import deepcopy

# 设置 GOOGLE_APPLICATION_CREDENTIALS 环境变量指向服务账号密钥文件
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'williamcloud.json'

def get_pet_reports(bucket_name, user_id, pet_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=f'{user_id}/pet/{pet_name}')
    
    report_files = []
    for blob in blobs:
        blob_name = blob.name[len(f'{user_id}/pet/'):]  # 获取报告的实际名称
        if blob_name.startswith(f'{pet_name}_') and (blob.name.endswith('.png') or blob.name.endswith('.jpg')):
            file_name = os.path.basename(blob.name)
            report_files.append(file_name)
    
    return sorted(report_files)
    


def create_report_bubble(pet_name, report_files, user_id):
    with open('historyreport.json', encoding='utf-8') as f:
        bubble = json.load(f)
    
    bubble['header']['contents'][0]['text'] = f"{pet_name} 的歷史報告"
    
    report_buttons = []
    client = storage.Client()
    bucket_name = 'william_001'
    for report in report_files:
        report_name = report.replace(f'{pet_name}_', '').replace('.png', '').replace('.jpg', '')
        
        
        
        blob_name = f"{user_id}/pet/{report}"
        blob = client.bucket(bucket_name).blob(blob_name)
        image_url = blob.public_url        
        
        # 查看報告按鈕
        button = deepcopy(bubble['body']['contents'][0])
        button['contents'][0]['action']['label'] = report_name
        button['contents'][0]['action']['uri'] = image_url
        
        button['contents'][1]['action']['label'] = "刪除"
        button['contents'][1]['action']['data'] = json.dumps({"action": "delete_report", "p_n": pet_name, "report_name": report})
        
        report_buttons.append(button)
 
    
    bubble['body']['contents'] = report_buttons  # 替換原始內容
    
    return bubble




if __name__ == "__main__":
# 调用函数示例
    bucket_name = 'william_001'
    pet_name = '威'
    user_id = 'U1fc284a7450faea47843af4fafa41ca0'
    report_files = get_pet_reports(bucket_name, user_id, pet_name)
    print(report_files)
    bubble = create_report_bubble(pet_name, report_files)
    print(json.dumps(bubble, indent=2, ensure_ascii=False))

