from flask import Flask, Flask, request, redirect, url_for, render_template
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
import json
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from image_uploade_pf import upload_image_to_gcs

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# 確保上傳目錄存在
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
current_script_dir = os.getcwd()
json_file_path = os.path.join(current_script_dir, 'pet_env.json')
# MongoDB 环境配置文件
with open(json_file_path, 'r') as f:
    env = json.load(f)
# ---------------MongoDB Connect---------------
uri = mongo_uri = env['MONGO_URI']

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
db = client['pet']
people_collection = db['users']
pets_collection = db['petfile']
# ----------------------------------------------
# client = MongoClient('mongodb://localhost:27017/')
# db = client.pet_management
# people_collection = db.people
# pets_collection = db.pets

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check_user/<uid>')
def check_user(uid):
    user = people_collection.find_one({'user_id': uid})
    if not user:
        return "用户不存在"

    if user['pets_tag'] == 0:
        return redirect(url_for('add_pet', uid=uid))
    else:
        return redirect(url_for('show_pet', uid=uid))

@app.route('/add_pet/<uid>', methods=['GET', 'POST'])
def add_pet(uid):
    if request.method == 'POST':
        try:
            name = request.form['name']
            gender = request.form['gender']
            breed = request.form['breed']
            birthdate = request.form['birthdate']
            vaccine_date = request.form['vaccineDate']
            profile_image = request.files['profileImage']
            pid = f"p{pets_collection.count_documents({}) + 1:02d}"

            if profile_image:
                filename = secure_filename(profile_image.filename)
                profile_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                profile_image.save(profile_image_path)
                
                with open(profile_image_path, 'rb') as file:
                    profile_image_url = upload_image_to_gcs(file, uid, pid)

            pet_data = {
                'pid': pid,
                'user_id': uid,
                'name': name,
                'gender': gender,
                'breed': breed,
                'birthdate': birthdate,
                'vaccineDate': vaccine_date,
                'profileImage': profile_image_url
            }
        except KeyError as e:
            return f"缺少必要的字段: {str(e)}", 400

        # 新增宠物资料
        pet_id = pets_collection.insert_one(pet_data).inserted_id

        # 更新用户的 pets_tag
        people_collection.update_one({'user_id': uid}, {'$inc': {'pets_tag': 1}})

        return redirect(url_for('show_pet', uid=uid))

    return render_template('add_pet.html', uid=uid)

@app.route('/show_pet/<uid>')
def show_pet(uid):
    pets = pets_collection.find({'user_id': uid})
    return render_template('show_pet.html', pets=pets, uid=uid)

@app.route('/edit_pet/<pid>', methods=['GET', 'POST'])
def edit_pet(pid):
    pet = pets_collection.find_one({'pid': pid})

    if not pet:
        print(f"宠物不存在: pid={pid}")  # 添加调试信息
        return "宠物不存在", 404

    if request.method == 'POST':
        try:
            updated_pet_data = {
                'name': request.form['name'],
                'gender': request.form['gender'],
                'breed': request.form['breed'],
                'birthdate': request.form['birthdate'],
                'vaccineDate': request.form['vaccineDate']
            }
            
            if 'profileImage' in request.files:
                profile_image = request.files['profileImage']
                if profile_image:
                    filename = secure_filename(profile_image.filename)
                    profile_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    profile_image.save(profile_image_path)
                    
                    with open(profile_image_path, 'rb') as file:
                        profile_image_url = upload_image_to_gcs(file, pet['user_id'], pid)
                    updated_pet_data['profileImage'] = profile_image_url

        except KeyError as e:
            return f"缺少必要的字段: {str(e)}", 400

        pets_collection.update_one(
            {'pid': pid},
            {'$set': updated_pet_data}
        )

        return redirect(url_for('show_pet', uid=pet['user_id']))

    return render_template('edit_pet.html', pet=pet, uid=pet['user_id'])


@app.route('/delete_pet/<pid>')
def delete_pet(pid):
    pet = pets_collection.find_one({'pid': pid})
    if pet:
        user_id = pet['user_id']
        pets_collection.delete_one({'pid': pid})

        # 更新用户的 pets_tag
        people_collection.update_one({'user_id': user_id}, {'$inc': {'pets_tag': -1}})

        return redirect(url_for('show_pet', uid=user_id))
    else:
        return "宠物不存在", 404

if __name__ == '__main__':
    app.run(debug=True)