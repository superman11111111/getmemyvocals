from asyncio import QueueEmpty
from glob import glob
import multiprocessing
from utils import disable_logging
import os
import re
from flask import Flask, render_template_string, send_from_directory, request, jsonify, send_file, make_response, Response, Request
from werkzeug.serving import run_simple
from utils import demucs_seperate
from pathlib import Path
import time
import tarfile
import shutil
import uuid
from multiprocessing import Process, Queue, Manager

app = Flask(__name__)

secret_password = "QtQWnTNnSAdN8Gr6mEPuTe8HRLrneVMBBb8SB4wL6LM9FTyf9UUNe6D5dG57GAdk"
port = 5000
debug = False
cookie_key = "sess"
max_queue_length = 100
helper_sleep = .5
compression = "xz"
files_dir = "files"

###

files_dir = os.path.join(os.getcwd(), files_dir)
app.debug = debug

if os.path.isdir(files_dir):
    shutil.rmtree(files_dir)
if os.path.isdir("separated"):
    shutil.rmtree("separated")
if not os.path.isdir(files_dir):
    os.mkdir(files_dir)
manager = Manager()
debug_currently_processing = manager.list()
file_register = manager.dict()
session_register = {}
session_status_register = {}
thread_queue = Queue(max_queue_length)
eraser_schedule = manager.dict()


def error(reason):
    return jsonify({"success": False, "reason": reason})


def error_bad_cookie():
    return jsonify({"success": False, "reason": "bad cookie"})


def error_bad_uid():
    return jsonify({"success": False, "reason": "bad uid"})


@app.route('/')
def hello_world():
    cookie = request.cookies.get(cookie_key)
    resp: Response = make_response(render_template_string(
        open("index.html", "r").read()))
    if not cookie or cookie not in session_register:
        cookie = register_session(request.remote_addr)
        resp.set_cookie(cookie_key, cookie, samesite="Lax")
    return resp


@app.route("/main.css")
def upload_css():
    return send_from_directory(".", "main.css")


@app.route("/main.js")
def upload_js():
    return send_from_directory(".", "main.js")


def secure_filename(filename):
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c == ' ']).rstrip()


@app.route("/secret/<string:password>", methods=["GET"])
def secret(password):
    if password == secret_password:
        return jsonify({"file_register": dict(file_register), "session_register": session_register, "session_status_register": session_status_register, "thread_queue": thread_queue.qsize(), "current_process": list(debug_currently_processing)})
    return error("wrong password")


@app.route("/reset/<string:password>", methods=["GET"])
def reset(password):
    if password == secret_password:
        executor_thread.terminate()
        if os.path.isdir(files_dir):
            shutil.rmftree(files_dir)
        if os.path.isdir("separated"):
            shutil.rmtree("separated")
        start_executor()
        return "restarted"
    return error("wrong password")


@app.route("/upload", methods=["POST"])
def upload():
    cookie = request.cookies.get(cookie_key)
    if not cookie or cookie not in session_register:
        return error_bad_cookie()
    file = request.files['afile']
    filename = file.filename
    fn_split = filename.split('.')
    file_extension = ''
    if len(fn_split) > 1:
        file_extension = '.' + secure_filename(fn_split[-1])
        filename = '.'.join(fn_split[:-1])
    filename = secure_filename(filename)
    filename += file_extension
    uid = register_file(files_dir, filename, True)
    print(file_register[uid]['path'])
    file.save(file_register[uid]['path'])
    session_status_register[cookie] = "upload"
    return jsonify({"success": True, "uid": uid, "alias": file_register[uid]['alias']})


def cleanup():
    tt = []
    while True:
        if tt:
            tt.clear()
        for uid, item in eraser_schedule.items():
            if time.time() >= item:
                tt.append(uid)
        for uid in tt:
            os.remove(file_register[uid]['path'])
            if 'archive' in file_register[uid]:
                os.remove(file_register[uid]['archive'])
            del file_register[uid]
            del eraser_schedule[uid]
        time.sleep(helper_sleep)


@app.route("/download/<string:uid>", methods=["GET"])
@disable_logging
def download_processed(uid):
    cookie = request.cookies.get(cookie_key)
    if not cookie or cookie not in session_register:
        return error_bad_cookie()
    if uid not in file_register:
        return error_bad_uid()
    while True:
        if "archive" in file_register[uid]:
            break
        time.sleep(.5)
    archive_path = file_register[uid]["archive"]
    alias = file_register[uid]['alias']
    eraser_schedule[uid] = time.time() + 60
    session_status_register[cookie] = "download"
    return send_file(archive_path, attachment_filename=alias + f".tar.{compression}", as_attachment=True)


def processing(in_uid, archive_path, file_register):
    separated_path = os.path.join(
        os.getcwd(), "separated", "mdx_extra_q", in_uid)
    print(separated_path, file_register[in_uid]["path"])
    demucs_seperate([Path(file_register[in_uid]["path"])])
    print("saving to", archive_path)
    with tarfile.open(archive_path, f"w:{compression}") as tar:
        tar.add(separated_path, arcname=file_register[in_uid]['alias'])
    shutil.rmtree(separated_path)
    tt = file_register[in_uid]
    tt['archive'] = archive_path
    file_register[in_uid] = tt
    print("now downloadable")


def add_thread(func, args):
    global thread_queue
    if thread_queue.qsize() < max_queue_length:
        thread_queue.put((func, args))
        return True
    return False


def thread_executor(thread_queue):
    while True:
        if not thread_queue.empty():
            func, args = thread_queue.get()
            debug_currently_processing.append(args)
            func(*args)
            debug_currently_processing.pop()
        time.sleep(helper_sleep)


@app.route("/process/<string:uid>", methods=["POST"])
def process_mp3(uid):
    cookie = request.cookies.get(cookie_key)
    if not cookie or cookie not in session_register:
        return error_bad_cookie()
    if uid not in file_register:
        return error_bad_uid()
    if cookie in session_status_register:
        if session_status_register[cookie] == "process":
            return error("You are already processing something")
    alias = file_register[uid]['alias']
    if not alias:
        alias = os.path.basename(file_register[uid]["path"])
    archive_path = file_register[uid]['path'] + f".tar.{compression}"
    added_thread = add_thread(processing, (uid, archive_path, file_register))
    if not added_thread:
        return error("Processing queue is full ;(")
    session_status_register[cookie] = "process"
    return jsonify({"success": True})


def register_file(path, alias=None, use_uid_as_filename=False):
    while True:
        uid = str(uuid.uuid4())
        if uid not in file_register:
            if use_uid_as_filename:
                assert alias is not None
                if os.path.isfile(path):
                    path = os.path.dirname(path)
                path = os.path.join(path, uid)
            file_register[uid] = {'path': path, 'alias': alias}
            return uid


def register_session(addr):
    while True:
        uid = str(uuid.uuid4())
        if uid not in session_register:
            session_register[uid] = addr
            return uid


def start_executor():
    global executor_thread, thread_queue
    executor_thread = Process(target=thread_executor, args=(thread_queue, ))
    executor_thread.daemon = False
    executor_thread.run
    executor_thread.start()


if __name__ == '__main__':
    start_executor()
    eraser_thread = Process(target=cleanup)
    eraser_thread.daemon = False
    eraser_thread.start()
    run_simple('0.0.0.0', port, app,
               use_reloader=True, use_debugger=True, use_evalex=True, threaded=True)
