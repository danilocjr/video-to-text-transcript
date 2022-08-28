# -*- encoding: UTF-8 -*-
from google.cloud import storage
from google.cloud import speech_v1p1beta1
from google.cloud.speech_v1p1beta1 import enums
from time import time

import os
import requests

def speechInfo():
    client = speech_v1p1beta1.SpeechClient.from_service_account_json('mdx-stt.json')
    config = {
        "language_code": "pt-BR",
        "encoding": "FLAC"
    }
    return{'client':client,'config':config, 'gs' : 'gs://mdx-hsr/'}

def storageInfo():
    sto_url = "https://storage.cloud.google.com/mdx-hsr/"
    sto_client = storage.Client.from_service_account_json('mdx-stt.json')
    sto_bucket = sto_client.bucket('mdx-hsr')
    return {'url':sto_url, 'client':sto_client, 'bucket':sto_bucket}

def uploadVideo(session):
    info = storageInfo()

    # Upload FULL Video
    blob_name = "{0}_FULL.mp4".format(session['project'])
    blob = info['bucket'].blob(blob_name)
    blob.upload_from_filename(session['video'])
    blob.make_public()
    deleteFile(session['video'])
    del session['video']
    session['videoURL'] = blob.public_url

    # Upload Excerpts
    for excerpt_id, excerpt_info in session['excerpts'].items():
        blob_name = "{0}_{1}.mp4".format(session['project'],excerpt_id)
        blob = info['bucket'].blob(blob_name)
        blob.upload_from_filename(excerpt_info['video'])
        blob.make_public()
        deleteFile(excerpt_info['video'])
        del excerpt_info['video']
        excerpt_info['videoURL'] = blob.public_url
        print("Uploading Video:{0}".format(blob_name))
    
    return session

def uploadAudio(session):
    info = storageInfo()

    # Upload FULL Audio
    blob_name = "{0}_FULL.flac".format(session['project'])
    blob = info['bucket'].blob(blob_name)
    blob.upload_from_filename(session['audio'])
    blob.make_public()
    deleteFile(session['audio'])
    del session['audio']
    session['audioURL'] = blob.public_url
    #print(session['audioURL'])

    # Upload Excerpts
    for excerpt_id, excerpt_info in session['excerpts'].items():
        blob_name = "{0}_{1}.flac".format(session['project'],excerpt_id)
        blob = info['bucket'].blob(blob_name)
        blob.upload_from_filename(excerpt_info['file'])
        blob.make_public()
        deleteFile(excerpt_info['file'])
        del excerpt_info['file']
        excerpt_info['audioURL'] = blob.public_url
        print("Uploading Audio:{0}".format(blob_name))
    
    return session

def uploadJSONFile(project,session):
    info = storageInfo()

    # Upload FULL Audio
    blob_name = "{0}.json".format(project)
    blob = info['bucket'].blob(blob_name)
    blob.upload_from_string(session)
    blob.make_public()
    print("Upload JSON Session file")

def getJSONFile(project):
    info = storageInfo()
    blob_name = "{0}.json".format(project)
    blob = info['bucket'].blob(blob_name)
    blob.download_to_filename("static/" + blob)
    print("Deleted JSON Session file")
    
def deleteJSONFile(project):
    info = storageInfo()
    blob_name = "{0}.json".format(project)
    blob = info['bucket'].blob(blob_name)
    blob.delete()
    print("Deleted JSON Session file")

def deleteFile(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)

def deleteBlob(fileURL):
    blob_name = fileURL.split('/mdx-hsr/',1)[1]
    info = storageInfo()
    blob = info['bucket'].blob(blob_name)
    blob.delete()