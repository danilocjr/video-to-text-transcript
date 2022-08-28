cd# -*- encoding: UTF-8 -*-
from flask import Flask
from flask import Response
from flask import redirect
from flask import request
from flask import session
from flask import jsonify
from flask import render_template as render
from flask import url_for
from flask import flash
from flask_cors import CORS, cross_origin

from controller import *

import shutil
import requests
import json
import os
import threading

app = Flask(__name__, instance_relative_config=True)

app.config["CORS_HEADERS"] = "Content-Type"
#cors_origins = "http://weblabtools-env.eba-gngkmpgm.us-east-1.elasticbeanstalk.com"
#cors_api_urls = [ r"/upload", r"/result", r"/result/search", r"/result/fulltext", r"/projects/get", r"/projects/del" ]

cors_origins = os.getenv('ORIGIN_DOMAIN')
print(">>> ORIGIN : {0}".format(cors_origins))

cors = CORS(app, resources={ 
                            r"/upload": {"origins": cors_origins},
                            r"/result": {"origins": cors_origins},
                            r"/result/search": {"origins": cors_origins},
                            r"/result/fulltext": {"origins": cors_origins},
                            r"/projects/get": {"origins": cors_origins},
                            r"/projects/del": {"origins": cors_origins},
                            r"/version": {"origins": cors_origins} 
                            }
            )

root = app.root_path
static = root + "/static/"

def download_file(url,local_filename):
    with requests.get(url, stream=True) as r:
        with open(local_filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
    return local_filename

# ======== GET PROJECTS
@app.route("/projects/get", methods=["GET"])
@cross_origin()
def projectsGet():
    return getProjectsList(static)


# ======== GET PROJECTS
@app.route("/projects/del", methods=["GET"])
@cross_origin()
def projectsDel():
    project = request.args.get("project")
    if project.strip() == "":
        raise Exception("false")
    session_path = static + project + "/"
    session_file = session_path + project + ".json"
    session = getSessionJson(session_file)
    if project:
        t = threading.Thread(target=deleteProjectAsync, args=(session, static))
        t.start()
        return {"response": project}

# ======== API HTTP TEST
@app.route("/version", methods=["GET"])
@cross_origin()
def version():
    return { "version" : "1.1" } 
    
# ======== UPLOAD FILES
@app.route("/upload", methods=["POST"])
@cross_origin()
def upload():
    if request.method == "POST":
        try:
            destPath = None

            mediaName = ""
            mediaPath = ""
            mediaType = ""
            form = request.form.to_dict()

            # Normalize project name
            projectName = form["project"].replace(" ","_")

            # Create project directory
            destPath = static + projectName + "/"
            os.mkdir(destPath)

            url = None
            if "url" in request.form:
                url = form["url"]
           
            if url != None and url != "":
                filename = url.split("/")[-1]
                mediaType = checkType(filename)
                mediaName = filename.split(".")[0]
                if mediaType == "Not supported":
                    raise Exception("Media Type Not Supported")
                mediaPath = destPath + filename                
                ret = download_file(url, mediaPath) ## PUT INSIDE THREAD
                print("Local Filename:{0}".format(ret))
            else:
                file = request.files["file"]
                mediaName = file.filename.split(".")[0]
                mediaType = checkType(file.filename)
                if mediaType == "Not supported":
                    os.rmdir(destPath)
                    raise Exception("Media Type Not Supported")
                mediaPath = destPath + file.filename
                file.save(mediaPath) ## PUT INSIDE THREAD

            ### --- REPLACE BY THREAD FUNCTION ---- ###
            
            # Assembling Session JSON
            session = {}
            session_file = "{0}.json".format(projectName)
            session_path = destPath + session_file

            session["status"] = "uploaded"
            session["project"] = projectName
            session["media-type"] = mediaType

            if mediaType == "video":  # Extracting Audio FLAC if video
                audioPath = destPath + mediaName + ".flac"
                session["video"] = mediaPath
                session["audio"] = audioPath
                saveJson(session_path, session)
                t = threading.Thread(target=extractAudioAsync, args=(session, destPath))
                t.start()
            else:
                session["audio"] = mediaPath
                saveJson(session_path, session)
                t = threading.Thread(
                    target=extractExcerptsAsync, args=(session, destPath)
                )
                t.start()

            # Save JSON with current status
            saveJson(session_path, session)

            ### --- REPLACE BY THREAD FUNCTION ---- ###
             
            # Realease control of HTTP request
            return {"response": "true"}

        except Exception as ex:
            if os.path.exists(destPath):
                os.rmdir(destPath)
            return {"response": str(ex)}


# ======== CHECK STATUS AND RESULTS
@app.route("/result", methods=["GET"])
@cross_origin()
def result():
    try:
        project = request.args.get("project")
        if project.strip() == "":
            raise Exception("PROJECT not provided in GET")
        session_file = static + project + "/" + project + ".json"
        return getSessionJson(session_file)
    except Exception as ex:
        return {"response": str(ex)}


@app.route("/result/search", methods=["GET"])
@cross_origin()
def search():
    try:
        project = request.args.get("project")
        if project.strip() == "":
            raise Exception("false")
        session_path = static + project + "/"
        session_file = session_path + project + ".json"
        session = getSessionJson(session_file)
        keywords_sentence = request.args.get("keywords")
        return keywordSearch(session, session_path, keywords_sentence)
    except Exception as ex:
        return {"response": str(ex)}


@app.route("/result/fulltext", methods=["GET"])
@cross_origin()
def fulltext():
    try:
        project = request.args.get("project")

        if project.strip() == "":
            raise Exception("PROJECT not provided in GET ")

        session_path = static + project + "/"
        session_file = session_path + project + ".json"
        session = getSessionJson(session_file)

        return getFulltext(session, session_path)

    except Exception as ex:
        return {"response": str(ex)}


if __name__ == "__main__":
    app.run()

