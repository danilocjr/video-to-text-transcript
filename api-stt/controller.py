# -*- encoding: UTF-8 -*-
from google.cloud import speech_v1p1beta1
from google.cloud.speech_v1p1beta1 import enums

from pydub import AudioSegment

# from pydub.silence import split_on_silence

import datetime
from fileHandle import *

import json
import subprocess
import os
import math
import threading
import time

# ------------- SESSION JSON METHODS ---------------
def saveJson(session_filepath, data):
    with open(session_filepath, "w") as file:
        json.dump(data, file)
    #jsons = json.dumps(data)
    #uploadJSONFile(data['project'],jsons)

def deleteJson(session_filepath):
    if os.path.exists(session_filepath):
        os.remove(session_filepath)
    #deleteJSONFile(project)

def updateStatusJson(session_filepath, status):
    if os.path.exists(session_filepath):
        session = {}
        with open(session_filepath, "r") as json_file:
            session = json.load(json_file)
        session["status"] = status
        saveJson(session_filepath, session)

def getSessionJson(session_filepath):
    session = {}

    if os.path.exists(session_filepath):
        with open(session_filepath, "r") as json_file:
            session = json.load(json_file)

    return session


# ------------- HELPERS ----------------------------
def checkType(filename):
    ext = filename.split(".")[-1]
    if ext.lower() in ["mp3", "wav", "flac"]:
        return "audio"
    elif ext.lower() in ["mp4", "ogg", "mkv"]:
        return "video"

    return "Not supported"

def convertMS(millis):
    seconds = (millis / 1000) % 60
    seconds = int(seconds)
    minutes = (millis / (1000 * 60)) % 60
    minutes = int(minutes)
    hours = (millis / (1000 * 60 * 60)) % 24
    str = "%02d:%02d:%02d" % (hours, minutes, seconds)
    return str


# ------------- HTTP ASYNC FUNCTS ------------------
def extractAudioAsync(session, destPath):
    # Extrai Audio do MP4
    print("Starting Audio Extraction")
    subprocess.call(
        "ffmpeg -i {0} -c:a flac -ac 1 -sample_fmt s16 -vn {1}".format(
            session["video"], session["audio"]
        ),
        shell=True,
    )
    
    while True:
        if os.path.exists(session["audio"]):
            print("Extraction Concluded")
            break
        time.sleep(2)
    
    extractExcerptsAsync(session, destPath)


def extractExcerptsAsync(session, destPath):
    excerpts = {}
    updateStatusJson(destPath + session["project"] + ".json", "Stage-1")
    
    # Create Excerpts from Audio
    print("[STAGE-1] Splitting Audio.")
    excerpts = splitAudioFile(session["audio"], destPath)
    session["audio"] = session["audio"].replace(".mp3", ".flac")
    session["excerpts"] = excerpts
    session["status"] = "Stage-2"
    saveJson(destPath + session["project"] + ".json", session)
    print("[STAGE-1] Splitting Audio Completed.")

    print("[STAGE-2] Uploading Audio")
    session = uploadAudio(session)
    saveJson(destPath + session["project"] + ".json", session)
    print("[STAGE-2] Uploading Completed.")

    print("[STAGE-2] Splitting Video")
    if session["media-type"] == "video":
        UploadVideoExcerpts(session, destPath)
    print("[STAGE-2] Splitting Video Completed.")
    
    print("[STAGE-3] Transcripting Started...")
    transcriptAsync(session, destPath)
    print("[STAGE-4] Transcripting Completed.")
    

def UploadVideoExcerpts(session, destPath):
    # Split video by Excerpts   
    splitVideoFile(session, destPath)    

    # Upload Videoclips Excerpts to GCS
    session = uploadVideo(session)
    session["status"] = "Stage-3"
    saveJson(destPath + session["project"] + ".json", session)


def transcriptAsync(session, destPath):
    infoSTT = speechInfo()
    session_filepath = destPath + session["project"] + ".json"
    for excerpt_id, excerpt_info in session["excerpts"].items():
        uri = infoSTT["gs"] + excerpt_info["audioURL"].split("/mdx-hsr/", 1)[1]
        audio = {"uri": uri} 
        print('Transcripting...{0}'.format(audio))
        response = infoSTT["client"].recognize(infoSTT["config"], audio)
        for result in response.results:
            alternative = result.alternatives[0]
            excerpt_info["text"] += format(alternative.transcript)
            excerpt_info["confidence"] = round(float(format(alternative.confidence)), 2)
     
        if not excerpt_info["confidence"]:
            try:
                deleteBlob(excerpt_info["audioURL"])
            except:
                pass
            
            del excerpt_info["audioURL"]
            
            if session["media-type"] == "video":
                try:
                    deleteBlob(excerpt_info["videoURL"])
                except:
                    pass
                del excerpt_info["videoURL"]
            #del session["excerpts"][excerpt_id]
        else:
            if session["media-type"] == "video":
                # Discard blob used in transcription
                try:
                    deleteBlob(excerpt_info["audioURL"])
                except:
                    pass
                del excerpt_info["audioURL"]
    
    session["status"] = "Stage-4"
    saveJson(destPath + session["project"] + ".json", session)


def keywordSearch(session, session_path, keywords):
    results = []
    # print(keywords)
    array_keywords = keywords.split(",")
    for excerpt_id, excerpt_info in session["excerpts"].items():
        if excerpt_info["text"]:
            kw_count = 0
            result_keywords = {}
            for keyword in array_keywords:
                kw_count_in_exc = 0
                st = " " + excerpt_info["text"].lower() + " "
                if "+" in keyword:
                    kws = keyword.split("+")
                    # print("st:"+st)
                    # print(kws)
                    kwOne = st.count(" {0} ".format(kws[0]).lower())
                    kwTwo = st.count(" {0} ".format(kws[1]).lower())
                    # print("ONE:"+kwOne+" | TWO:"+kwTwo)
                    kw_count_in_exc = max(kwOne, kwTwo)
                elif "*" in keyword:
                    kws = keyword.split("*")
                    kwOne = st.count(" {0} ".format(kws[0]).lower())
                    kwTwo = st.count(" {0} ".format(kws[1]).lower())
                    kw_count_in_exc = min(kwOne, kwTwo)
                else:
                    kw_count_in_exc = st.count(" {0} ".format(keyword).lower())

                # Include this keyword in the keywords results
                if kw_count_in_exc > 0:
                    result_keywords[keyword] = kw_count_in_exc
                    kw_count += kw_count_in_exc

            # Include this result in results
            if kw_count > 0:

                result = {}

                if session["media-type"] == "video":
                    result["mediaURL"] = excerpt_info["videoURL"]
                else:
                    result["mediaURL"] = excerpt_info["audioURL"]

                result["text"] = excerpt_info["text"]
                result["keyword-count"] = kw_count
                result["confidence"] = excerpt_info["confidence"]
                result["interval"] = excerpt_info["interval"]
                result["keywords"] = result_keywords
                # print(result)
                results.append(result)

    return json.dumps({"excerpts": results})


def getFulltext(session, session_path):

    results = {}
    text = ""
    avg_confidence = 0.0
    time_info = 0
    ex_count = 0
    for excerpt_id, excerpt_info in session["excerpts"].items():
        if excerpt_info["text"]:
            text += excerpt_info["text"] + "\n"
            avg_confidence += float(excerpt_info["confidence"])
            ex_count += 1
            if time_info > 5 * 4:  # 4 Chunks = 1 min, so 5x gives us each 5 minutes
                time_info = 0
                text += "\n" + excerpt_info["interval"] + "\n"
            time_info += 1

    if "videoURL" in session:
        results["mediaURL"] = session["videoURL"]
    else:
        results["mediaURL"] = session["audioURL"]

    print(results["mediaURL"])
    results["confidence"] = "{:.2f}".format(avg_confidence / ex_count)
    results["text"] = text

    return results


def getProjectsList(static):

    projectsList = []

    for r, d, f in os.walk(static):
        for file in f:
            if ".json" in file:
                # open JSON file
                array = json.load(open(os.path.join(r, file)))

                # get information needed
                projectInfo = {
                    "project": None,
                    "status": None,
                    "video": None,
                    "audio": None,
                    "created": None,
                }
                projectInfo["project"] = array["project"]
                projectInfo["status"] = array["status"]
                projectInfo["created"] = "%s" % datetime.datetime.fromtimestamp(
                    os.stat(os.path.join(r, file)).st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S")
                if "videoURL" in array:
                    projectInfo["video"] = array["videoURL"]
                elif "video" in array:
                    projectInfo["video"] = array["video"]

                if "audioURL" in array:
                    projectInfo["audio"] = array["audioURL"]
                elif "audio" in array:
                    projectInfo["audio"] = array["audio"]

                projectsList.append(projectInfo)

    return json.dumps(projectsList)


# ------------- CORE FUNCTS ------------------------
def splitAudioFile(filepath, destPath):
    excerpts = {}

    filename, extension = filepath.split(".")

    if "flac" not in extension:
        print("Converting to FLAC...")
        newFilepath = filename + ".flac"
        subprocess.call(
            "ffmpeg -i {0} -ac 1 -c:a flac {1}".format(filepath, newFilepath),
            shell=True,
        )
        deleteFile(filepath)
        filepath = newFilepath
        while True:
            if os.path.exists(newFilepath):
                print("MP3 Conversion Concluded...")
                break
            time.sleep(2)

    audio = AudioSegment.from_file(filepath, format="flac")
    audio_duration = len(audio)

    interval = 15 * 1000  # chunks de 15seg
    overlap = interval * 0.10
    cursor = 0  # initial chunk time
    fcursor = 0  # final chunk time
    excerptCount = 0
    for i in range(0, audio_duration, interval):
        fcursor = cursor + interval
        if fcursor > audio_duration:
            fcursor = audio_duration
        chunk = audio[cursor:fcursor]
        excerptFilename = "%sexcerpt-%4d.flac" % (destPath, excerptCount)
        chunk.export(excerptFilename, format="flac")
        excerpts[excerptCount] = {
            "time": [int(cursor / 1000), math.ceil(fcursor / 1000)],
            "text": "",
            "confidence": "",
            "interval": convertMS(cursor) + " ~ " + convertMS(fcursor),
            "file": excerptFilename,
        }
        print("Exporting Audio Excerpt:{0}".format(excerptCount))
        excerptCount += 1
        if fcursor == audio_duration:
            break
        cursor = fcursor - overlap

    return excerpts


def splitVideoFile(session, destPath):
    for excerpt_id, excerpt_info in session["excerpts"].items():
        time = excerpt_info["time"]
        clip_name = "{0}_{1}.mp4".format(session["project"], excerpt_id)
        clip_path = destPath + clip_name
        cmd = "ffmpeg -i {0} -vcodec libx264 -crf 24 -ss {1} -t {2} -c copy {3}".format(
            session["video"], time[0], time[1], clip_path
        )
        subprocess.call(cmd, shell=True)
        excerpt_info["video"] = clip_path
        print("Splitted Video Except:{0}".format(clip_name))
    return session


def deleteProjectAsync(session, static):
    # delete from GCS
    try:
        deleteBlob(session["audioURL"])
        print("Deleting Audio FULL in GCS")
    except:
        pass

    try:
        deleteBlob(session["videoURL"])
        print("Deleting Video FULL in GCS")
    except:
        pass

    # delete excerpts
    if "excerpts" in session:
        for excerpt_id, excerpt_info in session["excerpts"].items():
            if session["media-type"] == "video":
                try:
                    deleteBlob(excerpt_info["videoURL"])
                    print("Deleting Video Excerpt {0}".format(excerpt_info["videoURL"]))
                except:
                    pass
            else:
                try:
                    deleteBlob(excerpt_info["audioURL"])
                    print("Deleting Audio Excerpt {0}".format(excerpt_info["audioURL"]))
                except:
                    pass

    # delete local files
    projectFolder = static + session["project"]
    projectJSON = projectFolder + "/" + session["project"] + ".json"
    try:
        deleteFile(projectJSON)
        print("Deleting Project JSON")
    except:
        pass

    if os.path.exists(projectFolder):
        try:
            os.rmdir(projectFolder)
            print("Deleting Project Directory")
        except:
            pass
