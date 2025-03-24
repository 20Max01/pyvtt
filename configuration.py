
import json
import os

def read_configurations():
    """
    Reads the configuration settings from a JSON file named 'pyvtt.settings.json' 
    located in the same directory as the script.

    Returns:
        dict: The configuration settings loaded from the JSON file.

    Raises:
        Exception: If there is an error reading or parsing the JSON file, 
                   an exception is raised with the error details.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "pyvtt.settings.json")
    try:
        with open(settings_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading configurations: {e}")
        raise Exception(f"Error reading configurations: {e}")