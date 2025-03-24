#!/usr/bin/env python3
import sys
import subprocess
import os
import threading
import socket
import json
import requests
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread, pyqtSignal
from configuration import read_configurations
from notify import notify

CONFIGURATION = read_configurations()
CURRENT_PRESET = CONFIGURATION["presets"][0]  # Default to first preset

class WhisperWorker(QThread):
    """
    A PyQt QThread subclass that handles the transcription of audio files using Whisper 
    and processes the result with Ollama. The final output is copied to the clipboard 
    and a signal is emitted upon completion.
    Signals:
        finished (pyqtSignal): Emitted with the formatted transcription result as a string 
        when the process is successfully completed.
    Methods:
        run():
            Executes the transcription process using Whisper, sends the result to Ollama 
            for further processing, and copies the final output to the clipboard. Handles 
            errors at various stages and provides notifications for failures.
    """
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
            try:
                subprocess.run(whisper_cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Whisper Fehler: {e}")
                notify("Fehler", "Ein Fehler mit 'Whisper' ist aufgetreten!")
                return
            
            try:
                with open(CONFIGURATION["output_file"], "r") as f:
                    raw_result = f.read().strip().replace("\n", " ")
            except Exception as e:
                print(f"Datei Fehler: {e}")
                notify("Fehler", "Ein Fehler beim Lesen der Whisper-Ausgabe ist aufgetreten!")
                return
            
            print("Whisper Transkript erhalten.")

            # --- An Ollama schicken ---
            payload = {
                "model": CURRENT_PRESET["ollama_model"],
                "prompt": CURRENT_PRESET["ollama_prompt"] + raw_result,
                "stream": False
            }
            ollama_endpoint = f"{CONFIGURATION['ollama_url']}:{CONFIGURATION['ollama_port']}/api/generate"
            response = requests.post(ollama_endpoint, json=payload)

            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP Fehler: {e}")
                notify("Fehler", "Ein Fehler bei der Kommunikation mit 'Ollama' ist aufgetreten!")
                return

            formatted_result = response.json().get("response", "").strip()
            formatted_result = "\n".join(line.strip() for line in formatted_result.splitlines())
            print("Ollama Antwort erhalten.")

            # Ergebnis ins Clipboard kopieren
            try:
                subprocess.run(["wl-copy"], input=formatted_result.encode(), check=True)
            except subprocess.CalledProcessError as e:
                print(f"Clipboard Fehler: {e}")
                notify("Fehler", "Ein Fehler beim Kopieren des Ergebnisses ist aufgetreten!")
                return
            
            notify("Spracherkennung", "Transkription abgeschlossen!")
            self.finished.emit(formatted_result)

        except Exception as e:
            print(f"Fehler: {e}")
            notify("Fehler", "Ein Fehler ist aufgetreten!")
            return

class SocketListener(threading.Thread):
    """
    A thread-based socket listener for handling inter-process communication
    via a UNIX domain socket. This class listens for specific commands
    ("toggle", "start", "stop") sent to the socket and triggers corresponding
    methods in the provided tray application instance.

    Attributes:
        tray_app (object): The tray application instance that provides methods
            for handling recording actions.
        sock (socket.socket): The UNIX domain socket used for communication.

    Methods:
        run():
            Continuously listens for incoming connections on the socket.
            Processes received commands and invokes the appropriate methods
            on the tray application instance.
    """
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

class TrayApp:
    """
    TrayApp is a system tray application that provides voice-to-text functionality. It allows users to manage presets, 
    start and stop audio recording, and process the recorded audio using a WhisperWorker.

    Attributes:
        app (QApplication): The main application instance.
        tray (QSystemTrayIcon): The system tray icon for the application.
        menu (QMenu): The context menu for the system tray icon.
        preset_actions (list): A list of QAction objects representing the preset options.
        preset_group (QMenu): A submenu for managing presets.
        quit_action (QAction): An action to quit the application.
        recording_process (subprocess.Popen or None): The process handling audio recording.
        socket_listener (SocketListener): A listener for socket communication.
        worker (WhisperWorker or None): A worker thread for processing audio with Whisper.

    Methods:
        __init__(): Initializes the TrayApp instance, setting up the system tray, menu, and socket listener.
        set_preset(index): Sets the active preset based on the given index and updates the UI.
        start_recording(): Starts audio recording using ffmpeg.
        stop_recording_if_possible(): Stops the audio recording process if it is running.
        toggle_recording(): Toggles between starting and stopping the audio recording.
        start_whisper_worker(): Starts a WhisperWorker thread to process the recorded audio.
        show_result(text): Displays the processed text result from the WhisperWorker.
        cleanup(): Cleans up resources, such as removing the socket file, before the application exits.
        run(): Starts the application's event loop.
    """
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.tray = QSystemTrayIcon(QIcon.fromTheme("audio-input-microphone"))
        self.menu = QMenu()

        self.app.aboutToQuit.connect(self.cleanup)

        # Preset Menü
        self.preset_actions = []
        self.preset_group = QMenu("Presets")
        for i, preset in enumerate(CONFIGURATION["presets"]):
            action = QAction(preset["name"], self.menu)
            action.setCheckable(True)
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