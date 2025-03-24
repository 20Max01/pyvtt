import subprocess

def notify(title: str, message: str) -> None:
    """
    Sends a desktop notification using the `notify-send` command.

    Args:
        title (str): The title of the notification.
        message (str): The message content of the notification.

    Raises:
        subprocess.CalledProcessError: If the `notify-send` command fails.

    Note:
        This function requires the `notify-send` command to be available on the system.
        It is typically available on Linux systems with a notification daemon running.
    """
    try:
        subprocess.run(["notify-send", "-a", "Voice to Text", "-i", "audio-input-microphone", title, message], check=True)
    except subprocess.CalledProcessError as e:
        print("Fehler beim Benachrichtigen mit 'notify-send'.")
        print(e)