import json
from google.cloud import storage
import os
from copy import deepcopy

# 设置 GOOGLE_APPLICATION_CREDENTIALS 环境变量指向服务账号密钥文件
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\Users\T14 Gen 3\Desktop\pydm\vm_01\williamcloud.json'

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


# def get_pet_reports(bucket_name, pet_name):
#     client = storage.Client()
#     bucket = client.bucket(bucket_name)
#     blobs = bucket.list_blobs(prefix=f'pet/{pet_name}')
    
#     report_files = []
#     for blob in blobs:
#         if blob.name.endswith('.png') or blob.name.endswith('.jpg'):
#             file_name = os.path.basename(blob.name)
#             report_files.append(file_name)
    
#     return sorted(report_files)

def create_report_bubble(pet_name, report_files):
    with open(r'C:\Users\T14 Gen 3\Desktop\pydm\vm_01\historyreport.json', encoding='utf-8') as f:
        bubble = json.load(f)
    
    bubble_template = bubble['body']['contents'][0]
    bubble['header']['contents'][0]['text'] = f"{pet_name} 的歷史報告"
    
    for report in report_files:
        report_name = report.replace('.png', '').replace('_', ' ')  # 移除 '.png'
        button = deepcopy(bubble_template)
        button['action']['label'] = report_name  # 將按鈕標籤設置為移除 ".png" 後的圖片名稱
        button['action']['type'] = 'postback'
        button['action']['data'] = json.dumps({"action": "view_report", "p_n": pet_name, "report_name": report})
        bubble['body']['contents'].append(button)
    
    bubble['body']['contents'].pop(0)  # 移除模板中的原始內容
    
    return bubble

# def create_report_bubble(pet_name, report_files):
#     with open(r'C:\Users\T14 Gen 3\Desktop\pycd\pet_11\pet_fourV_py\historyreport.json', encoding='utf-8') as f:
#         bubble = json.load(f)
    
#     bubble_template = bubble['body']['contents'][0]
#     bubble['header']['contents'][0]['text'] = f"{pet_name} 的歷史報告"
    
#     for report in report_files:
#         year = report.split('_')[1].split('.')[0]
#         button = deepcopy(bubble_template)
#         button['action']['label'] = year
#         button['action']['type'] = 'postback'
#         button['action']['data'] = json.dumps({"action": "view_report", "pet_name": pet_name, "year": year})
#         bubble['body']['contents'].append(button)
    
#     bubble['body']['contents'].pop(0)
    
#     return bubble



if __name__ == "__main__":
# 调用函数示例
    bucket_name = 'william_001'
    pet_name = '威'
    user_id = 'U1fc284a7450faea47843af4fafa41ca0'
    report_files = get_pet_reports(bucket_name, user_id, pet_name)
    print(report_files)
    bubble = create_report_bubble(pet_name, report_files)
    print(json.dumps(bubble, indent=2, ensure_ascii=False))
