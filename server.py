from utils import disable_logging
import os
import re
from flask import Flask, render_template_string, send_from_directory, request, jsonify, send_file, make_response, Response, Request
from werkzeug.serving import run_simple
from utils import main as demucs_seperate
from pathlib import Path
import time
import tarfile
import shutil
from threading import Thread
import uuid

app = Flask(__name__)

secret_password = "QtQWnTNnSAdN8Gr6mEPuTe8HRLrneVMBBb8SB4wL6LM9FTyf9UUNe6D5dG57GAdk"
app.debug = True
# app.debug = False
files_dir = os.path.join(os.getcwd(), "files")

if os.path.isdir(files_dir):
    shutil.rmtree(files_dir)
if os.path.isdir("separated"):
    shutil.rmtree("separated")
if not os.path.isdir(files_dir):
    os.mkdir(files_dir)

file_register = {}
session_register = {}
session_status_register = {}

cookie_key = "sess"
# max_threads = 1
thread_queue = []
max_queue_length = 100
debug_currently_processing = []
eraser_schedule = {}
helper_sleep = .5
# threads = {}


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
        resp.set_cookie(cookie_key, cookie, secure=True)
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
        return jsonify({"file_register": file_register, "session_register": session_register, "session_status_register": session_status_register, "thread_queue": [(str(func), args) for func, args in thread_queue], "current_process": debug_currently_processing})
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
        for uid in eraser_schedule:
            if time.time() >= eraser_schedule[uid]:
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
    # uid = 'bb2c790e-16f0-46c8-a127-5497ff5c146c'
    if "archive" not in file_register[uid]:
        return jsonify({"success": True, "fileReady": False})
    archive_path = file_register[uid]["archive"]
    alias = file_register[uid]['alias']
    # del file_register[uid]
    eraser_schedule[uid] = time.time() + 60
    session_status_register[cookie] = "download"
    return send_file(archive_path, attachment_filename=alias + ".tar.gz", as_attachment=True)


def processing(in_uid, archive_path):
    separated_path = os.path.join(
        os.getcwd(), "separated", "mdx_extra_q", in_uid)
    print(separated_path, file_register[in_uid]["path"])
    demucs_seperate([Path(file_register[in_uid]["path"])])
    print("saving to", archive_path)
    # for f in os.listdir(separated_path):
    #     print(os.path.getsize(os.path.join(separated_path, f)))
    # time.sleep(1)
    # for f in os.listdir(separated_path):
    #     print(os.path.getsize(os.path.join(separated_path, f)))
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(separated_path, arcname=file_register[in_uid]['alias'])
    shutil.rmtree(separated_path)
    file_register[in_uid]['archive'] = archive_path

    # del threads[thread_id]


def add_thread(func, args):
    if len(thread_queue) < max_queue_length:
        thread_queue.append((func, args))
        return True
    return False


def thread_executor():
    while True:
        if thread_queue:
            func, args = thread_queue.pop(0)
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
    archive_path = file_register[uid]['path'] + ".tar.gz"
    added_thread = add_thread(processing, (uid, archive_path))
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
            file_register[uid] = {"path": path, "alias": alias}
            return uid


def register_session(addr):
    while True:
        uid = str(uuid.uuid4())
        if uid not in session_register:
            session_register[uid] = addr
            return uid


if __name__ == '__main__':
    executor_thread = Thread(target=thread_executor)
    executor_thread.daemon = False
    executor_thread.start()
    eraser_thread = Thread(target=cleanup)
    eraser_thread.daemon = False
    eraser_thread.start()
    run_simple('localhost', 5000, app,
               use_reloader=True, use_debugger=True, use_evalex=True)
