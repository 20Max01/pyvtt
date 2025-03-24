#!/usr/bin/env python3
import sys
import subprocess
import os
import threading
import socket
import json
import requests
import json
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread, pyqtSignal

# === Config ===
def read_configurations():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "pyvtt.settings.json")
    with open(settings_path) as f:
        return json.load(f)

CONFIGURATION = read_configurations()
CURRENT_PRESET = CONFIGURATION["presets"][0]  # Default to first preset

def notify(title: str, message: str) -> None:
    try:
        subprocess.run(["notify-send", "-a", "Voice to Text", "-i", "audio-input-microphone", title, message], check=True)
    except subprocess.CalledProcessError as e:
        print("Fehler beim Benachrichtigen mit 'notify-send'.")
        print(e)

# === Worker Thread for Whisper + Ollama ===
class WhisperWorker(QThread):
    finished = pyqtSignal(str)

    def run(self):
        try:
            # Whisper ausführen
            whisper_cmd = [
                CONFIGURATION["whisper_path"],
                "-m", CURRENT_PRESET["whisper_model"],
                "-f", CONFIGURATION["audio_file"],
                "-l", CURRENT_PRESET["language"],
                "-otxt",
                "-of", CONFIGURATION["output_file"].replace(".txt", "")
            ]
            subprocess.run(whisper_cmd, check=True)
            with open(CONFIGURATION["output_file"], "r") as f:
                raw_result = f.read().strip().replace("\n", " ")
            print("Whisper Transkript erhalten.")

            # --- An Ollama schicken ---
            payload = {
                "model": CURRENT_PRESET["ollama_model"],
                "prompt": CURRENT_PRESET["ollama_prompt"] + raw_result,
                "stream": False
            }
            ollama_endpoint = f"{CONFIGURATION['ollama_url']}:{CONFIGURATION['ollama_port']}/api/generate"
            response = requests.post(ollama_endpoint, json=payload)
            response.raise_for_status()
            formatted_result = response.json().get("response", "").strip()
            formatted_result = "\n".join(line.strip() for line in formatted_result.splitlines())
            print("Ollama Antwort erhalten.")

            # Ergebnis ins Clipboard kopieren
            subprocess.run(["wl-copy"], input=formatted_result.encode(), check=True)
            notify("Spracherkennung", "Transkription abgeschlossen!")
            self.finished.emit(formatted_result)

        except Exception as e:
            notify("Fehler", "Ein Fehler ist aufgetreten!")
            print(f"Fehler: {e}")

# === Socket Listener Thread ===
class SocketListener(threading.Thread):
    def __init__(self, tray_app):
        super().__init__(daemon=True)
        self.tray_app = tray_app
        if os.path.exists(CONFIGURATION["socket_path"]):
            os.remove(CONFIGURATION["socket_path"])
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(CONFIGURATION["socket_path"])
        os.chmod(CONFIGURATION["socket_path"], 0o666)
        self.sock.listen(1)

    def run(self):
        while True:
            conn, _ = self.sock.accept()
            with conn:
                data = conn.recv(1024).decode().strip()
                if data == "toggle":
                    self.tray_app.toggle_recording()
                elif data == "start":
                    self.tray_app.start_recording()
                elif data == "stop":
                    self.tray_app.stop_recording_if_possible()

# === Tray Application ===
class TrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.tray = QSystemTrayIcon(QIcon.fromTheme("audio-input-microphone"))
        self.menu = QMenu()

        self.app.aboutToQuit.connect(self.cleanup)

        # Preset Menü
        self.preset_actions = []
        self.preset_group = QMenu("Presets")
        for i, preset in enumerate(CONFIGURATION["presets"]):
            action = QAction(preset["name"], self.menu, checkable=True)
            if i == 0:
                action.setChecked(True)
            action.triggered.connect(lambda checked, index=i: self.set_preset(index))
            self.preset_group.addAction(action)
            self.preset_actions.append(action)
        self.menu.addMenu(self.preset_group)

        # Quit
        self.quit_action = QAction("Beenden")
        self.quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip("Voice to Text")
        self.tray.show()

        self.recording_process = None

        self.socket_listener = SocketListener(self)
        self.socket_listener.start()

    def set_preset(self, index):
        global CURRENT_PRESET
        print(f"Preset gewechselt: {CONFIGURATION['presets'][index]['name']}")
        CURRENT_PRESET = CONFIGURATION["presets"][index]
        # Nur einer darf gecheckt sein
        for i, action in enumerate(self.preset_actions):
            action.setChecked(i == index)

    def start_recording(self):
        if self.recording_process is None:
            print("Starte Aufnahme...")
            self.recording_process = subprocess.Popen([
                "ffmpeg", "-f", "pulse", "-i", "default", "-ar", "16000",
                "-ac", "1", CONFIGURATION["audio_file"], "-y", "-loglevel", "quiet"
            ])
            notify("Aufnahme", "Aufnahme gestartet!")

    def stop_recording_if_possible(self):
        if self.recording_process:
            print("Stoppe Aufnahme...")
            self.recording_process.terminate()
            self.recording_process.wait()
            self.recording_process = None
            notify("Aufnahme", "Aufnahme beendet, verarbeite...")
            self.start_whisper_worker()

    def toggle_recording(self):
        if self.recording_process:
            self.stop_recording_if_possible()
        else:
            self.start_recording()

    def start_whisper_worker(self):
        self.worker = WhisperWorker()
        self.worker.finished.connect(self.show_result)
        self.worker.start()

    def show_result(self, text):
        print(f"Fertig:\n{text}")

    def cleanup(self):
        if os.path.exists(CONFIGURATION["socket_path"]):
            os.remove(CONFIGURATION["socket_path"])
        print("Socket sauber entfernt.")

    def run(self):
        sys.exit(self.app.exec_())

if __name__ == "__main__":
    TrayApp().run()