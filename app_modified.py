import os
import io
import json
import numpy as np
import tensorflow as tf
from flask import Flask, render_template, request, redirect, url_for, jsonify
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google.oauth2 import service_account
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

app = Flask(__name__)

# Load Google Drive API credentials
SERVICE_ACCOUNT_FILE = "herb-image-search-fd5324031218.json"  # Replace with your JSON file path
SCOPES = ["https://www.googleapis.com/auth/drive"]
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=credentials)

# Google Drive folder containing models
GOOGLE_DRIVE_FOLDER_ID = "1pwZbzsHpnYK_seLqa2dn6VK6QKzI5LAP"  # Replace with your folder ID
UPLOADS_FOLDER_ID = "1Q-B9dx7w6vb8UjQC46VMAO_qSUkdjVVV"  # Replace with your upload folder ID

# Temporary storage for downloaded models
MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

# Retrieve available herb families
def get_families():
    query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    #return {folder["name"]: folder["id"] for folder in results.get("files", [])}
    return {folder["name"]: folder["id"] for folder in results.get("files", []) if folder["name"] != "Common Herbs"}


families = get_families()
families = dict(sorted(families.items()))
print(families)

# Retrieve species list dynamically
def get_species_mapping(family):
    species_mapping = {}
    if family not in families:
        return species_mapping

    dataset_folder_query = f"'{families[family]}' in parents and name='1)dataset_for_model'"
    dataset_folder = drive_service.files().list(q=dataset_folder_query, fields="files(id, name)").execute().get("files", [])

    if not dataset_folder:
        return species_mapping

    train_folder_query = f"'{dataset_folder[0]['id']}' in parents and name='train'"
    train_folder = drive_service.files().list(q=train_folder_query, fields="files(id, name)").execute().get("files", [])

    if not train_folder:
        return species_mapping

    species_query = f"'{train_folder[0]['id']}' in parents and mimeType='application/vnd.google-apps.folder'"
    species_folders = drive_service.files().list(q=species_query, fields="files(id, name)").execute().get("files", [])
    print(species_folders)
    species_folders = species_folders[::-1]

    print(species_folders)

    for index, species in enumerate(species_folders):
        species_mapping[index] = species["name"]

    print(f"Species mapping for family {id}: {species_mapping}")

    return species_mapping

# Load herb classification model
def load_model(family):
    model_path = os.path.join(MODEL_DIR, f"{family}.h5")

    if not os.path.exists(model_path):
        query = f"'{families[family]}' in parents and name='{family}.h5'"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        
        if files:
            file_id = files[0]["id"]
            request = drive_service.files().get_media(fileId=file_id)
            with open(model_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

    return tf.keras.models.load_model(model_path) if os.path.exists(model_path) else None

# Image classification
def classify_image(imageFile, model, species_mapping):
    img = Image.open(imageFile).resize((224, 224), Image.Resampling.LANCZOS)
    x = preprocess_input(np.expand_dims(image.img_to_array(img), axis=0))
    pred = model.predict(x)
    
    predicted_index = np.argmax(pred, axis=1)[0]
    species_name = species_mapping.get(predicted_index, "Unknown Species")

    print("Families available:", families.keys())
    #print("Requested family:", family)

    print("Predicted Index:", predicted_index)
    print("Available Mappings:", species_mapping.keys())


    return species_name

# Homepage
@app.route("/")
def main():
    return render_template("index.html")

# Upload image
@app.route("/upload", methods=["GET", "POST"])
def upload_image():
    message = None  # Initialize message variable
    if request.method == "POST":
        file = request.files["image"]
        if file:
            file_metadata = {"name": file.filename, "parents": [UPLOADS_FOLDER_ID]}
            media = MediaIoBaseUpload(file, mimetype=file.content_type, resumable=True)
            drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            message = "Image uploaded successfully to our database!"  # Set success message
    return render_template("upload.html", message=message)



# Common herb classification

@app.route("/common_classification", methods=["GET", "POST"])
def common_classification():
    if request.method == "POST":
        global families
        file = request.files["image"]
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        families = {folder["name"]: folder["id"] for folder in results.get("files", [])}
        #return {folder["name"]: folder["id"] for folder in results.get("files", []) if folder["name"] != "Common Herbs"}
        model = load_model("Common Herbs")
        species_mapping = get_species_mapping("Common Herbs")
        print(species_mapping)
        prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        #families = {folder["name"]: folder["id"] for folder in results.get("files", [])}
        families = {folder["name"]: folder["id"] for folder in results.get("files", []) if folder["name"] != "Common Herbs"}
        return jsonify({"prediction": prediction})  # Returning JSON response
    return render_template("common_classification.html")


@app.route('/common_herbs')
def common_herbs():
    return render_template('common_herbs.html')


# @app.route("/common_classification", methods=["GET", "POST"])
# def common_classification():
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model("Common Herbs")
#         species_mapping = get_species_mapping("Common Herbs")
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return jsonify({"prediction": prediction})

#     return render_template("common_classification.html")



# # Common herb classification
# @app.route("/common_classification", methods=["GET", "POST"])
# def common_classification():
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model("Common Herbs")
#         species_mapping = get_species_mapping("Common Herbs")
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("common_classification.html")

# Family classification selection page
@app.route("/family_classification")
def family_classification():
    return render_template("family_classification.html", families=families.keys())


# Classification for a specific family

@app.route("/family/<family>", methods=["GET", "POST"])
def family_model(family):
    if request.method == "POST":
        file = request.files["image"]
        model = load_model(family)
        species_mapping = get_species_mapping(family)
        prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
        return jsonify({"prediction": prediction})  # Returning JSON response
    return render_template("classify.html", family=family)


# @app.route("/family/<family>", methods=["GET", "POST"])
# def family_model(family):
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model(family)
#         species_mapping = get_species_mapping(family)
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return jsonify({"prediction": prediction})

#     return render_template("classify.html", family=family)



# # Classification for a specific family
# @app.route("/family/<family>", methods=["GET", "POST"])
# def family_model(family):
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model(family)
#         species_mapping = get_species_mapping(family)
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("classify.html", family=family)

if __name__ == "__main__":
    app.run(debug=True)






# import os
# import json
# import numpy as np
# import tensorflow as tf
# from flask import Flask, render_template, request
# from PIL import Image
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseDownload
# from google.oauth2 import service_account
# from tensorflow.keras.preprocessing import image
# from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

# app = Flask(__name__)

# # Load Google Drive API credentials
# SERVICE_ACCOUNT_FILE = "herb-image-search-fd5324031218.json"  # Replace with your JSON file path
# SCOPES = ["https://www.googleapis.com/auth/drive"]
# credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
# drive_service = build("drive", "v3", credentials=credentials)

# # Google Drive base folder
# GOOGLE_DRIVE_FOLDER_ID = "1ITtIRG8DGae_yR1PjO9jE6199MM3Su6Y"  # Replace with your base folder ID
# UPLOADS_FOLDER_ID = "1Q-B9dx7w6vb8UjQC46VMAO_qSUkdjVVV"  # Replace with your upload folder ID

# # Model storage directory
# MODEL_DIR = "models"
# os.makedirs(MODEL_DIR, exist_ok=True)

# def get_families():
#     categories = {"Monocots": {}, "Dicots": {}}
    
#     query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
#     results = drive_service.files().list(q=query, fields="files(id, name)").execute()
#     category_folders = {folder["name"]: folder["id"] for folder in results.get("files", [])}
    
#     for category in ["Monocots", "Dicots"]:
#         if category in category_folders:
#             query = f"'{category_folders[category]}' in parents and mimeType='application/vnd.google-apps.folder'"
#             results = drive_service.files().list(q=query, fields="files(id, name)").execute()
#             categories[category] = {folder["name"]: folder["id"] for folder in results.get("files", [])}
    
#     return categories

# families = get_families()

# def get_species_mapping(category, family):
#     species_mapping = {}
#     if category not in families or family not in families[category]:
#         return species_mapping
    
#     family_id = families[category][family]
#     dataset_folder_query = f"'{family_id}' in parents and name='1)dataset_for_model'"
#     dataset_folder = drive_service.files().list(q=dataset_folder_query, fields="files(id, name)").execute().get("files", [])
    
#     if not dataset_folder:
#         return species_mapping
    
#     train_folder_query = f"'{dataset_folder[0]['id']}' in parents and name='train'"
#     train_folder = drive_service.files().list(q=train_folder_query, fields="files(id, name)").execute().get("files", [])
    
#     if not train_folder:
#         return species_mapping
    
#     species_query = f"'{train_folder[0]['id']}' in parents and mimeType='application/vnd.google-apps.folder'"
#     species_folders = drive_service.files().list(q=species_query, fields="files(id, name)").execute().get("files", [])
    
#     for index, species in enumerate(species_folders):
#         species_mapping[index] = species["name"]
    
#     return species_mapping

# def load_model(category, family):
#     model_path = os.path.join(MODEL_DIR, f"{family}.h5")
    
#     if not os.path.exists(model_path):
#         query = f"'{families[category][family]}' in parents and name='{family}.h5'"
#         results = drive_service.files().list(q=query, fields="files(id, name)").execute()
#         files = results.get("files", [])
        
#         if files:
#             file_id = files[0]["id"]
#             request = drive_service.files().get_media(fileId=file_id)
#             with open(model_path, "wb") as f:
#                 downloader = MediaIoBaseDownload(f, request)
#                 done = False
#                 while not done:
#                     status, done = downloader.next_chunk()
    
#     return tf.keras.models.load_model(model_path) if os.path.exists(model_path) else None

# def classify_image(imageFile, model, species_mapping):
#     img = Image.open(imageFile).resize((224, 224), Image.Resampling.LANCZOS)
#     x = preprocess_input(np.expand_dims(image.img_to_array(img), axis=0))
#     pred = model.predict(x)
#     predicted_index = np.argmax(pred, axis=1)[0]
#     return species_mapping.get(predicted_index, "Unknown Species")

# @app.route("/")
# def main():
#     return render_template("index.html")

# # Upload image
# @app.route("/upload", methods=["GET", "POST"])
# def upload_image():
#     if request.method == "POST":
#         file = request.files["image"]
#         if file:
#             file_metadata = {"name": file.filename, "parents": [UPLOADS_FOLDER_ID]}
#             media = MediaIoBaseUpload(file, mimetype=file.content_type, resumable=True)
#             drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
#             return "Image uploaded successfully!"
#     return render_template("upload.html")

# # Common herb classification
# @app.route("/common_classification", methods=["GET", "POST"])
# def common_classification():
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model("Common_Herbs")
#         species_mapping = get_species_mapping("Common_Herbs")
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("common_classification.html")


# @app.route("/family_classification")
# def family_classification():
#     return render_template("family_classification.html", families=families)

# @app.route("/family/<category>/<family>", methods=["GET", "POST"])
# def family_model(category, family):
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model(category, family)
#         species_mapping = get_species_mapping(category, family)
#         prediction = classify_image(file, model, species_mapping) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("classify.html", category=category, family=family)



# if __name__ == "__main__":
#     app.run(debug=True)














# import os
# import io
# import json
# import numpy as np
# import tensorflow as tf
# from flask import Flask, render_template, request, redirect, url_for
# from PIL import Image
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
# from google.oauth2 import service_account
# from tensorflow.keras.preprocessing import image
# from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

# app = Flask(__name__)

# # Load Google Drive API credentials
# SERVICE_ACCOUNT_FILE = "herb-image-search-fd5324031218.json"  # Replace with your JSON file path
# SCOPES = ["https://www.googleapis.com/auth/drive"]
# credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
# drive_service = build("drive", "v3", credentials=credentials)

# # Google Drive folder containing models
# GOOGLE_DRIVE_FOLDER_ID = "1pwZbzsHpnYK_seLqa2dn6VK6QKzI5LAP"  # Replace with your folder ID
# UPLOADS_FOLDER_ID = "1Q-B9dx7w6vb8UjQC46VMAO_qSUkdjVVV"  # Replace with your upload folder ID

# # Temporary storage for downloaded models
# MODEL_DIR = "models"
# os.makedirs(MODEL_DIR, exist_ok=True)

# # Retrieve available herb families
# def get_families():
#     query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
#     results = drive_service.files().list(q=query, fields="files(id, name)").execute()
#     return {folder["name"]: folder["id"] for folder in results.get("files", [])}

# families = get_families()

# # Load herb classification model
# def load_model(family):
#     model_path = os.path.join(MODEL_DIR, f"{family}.h5")

#     if not os.path.exists(model_path):
#         query = f"'{families[family]}' in parents and name='{family}.h5'"
#         results = drive_service.files().list(q=query, fields="files(id, name)").execute()
#         files = results.get("files", [])
        
#         if files:
#             file_id = files[0]["id"]
#             request = drive_service.files().get_media(fileId=file_id)
#             with open(model_path, "wb") as f:
#                 downloader = MediaIoBaseDownload(f, request)
#                 done = False
#                 while not done:
#                     status, done = downloader.next_chunk()

#     return tf.keras.models.load_model(model_path) if os.path.exists(model_path) else None

# # Image classification
# def classify_image(imageFile, model):
#     img = Image.open(imageFile).resize((224, 224), Image.Resampling.LANCZOS)
#     x = preprocess_input(np.expand_dims(image.img_to_array(img), axis=0))
#     pred = model.predict(x)
#     return np.argmax(pred, axis=1)[0]

# # Homepage
# @app.route("/")
# def main():
#     return render_template("index.html")

# # Upload image
# @app.route("/upload", methods=["GET", "POST"])
# def upload_image():
#     if request.method == "POST":
#         file = request.files["image"]
#         if file:
#             file_metadata = {"name": file.filename, "parents": [UPLOADS_FOLDER_ID]}
#             media = MediaIoBaseUpload(file, mimetype=file.content_type, resumable=True)
#             drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
#             return "Image uploaded successfully!"
#     return render_template("upload.html")

# # Common herb classification
# @app.route("/common_classification", methods=["GET", "POST"])
# def common_classification():
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model("Common_Herbs")
#         prediction = classify_image(file, model) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("common_classification.html")

# # Family classification selection page
# @app.route("/family_classification")
# def family_classification():
#     return render_template("family_classification.html", families=families.keys())

# # Classification for a specific family
# @app.route("/family/<family>", methods=["GET", "POST"])
# def family_model(family):
#     if request.method == "POST":
#         file = request.files["image"]
#         model = load_model(family)
#         prediction = classify_image(file, model) if model else "Error: Model not found"
#         return render_template("result.html", prediction=prediction)
#     return render_template("classify.html", family=family)

# if __name__ == "__main__":
#     app.run(debug=True)
