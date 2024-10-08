from collections import deque
import cv2
import logging
import mediapipe as mp
import numpy as np
import os
import pickle
import pygame
from threading import Thread
import time

from config import ARTIFACTS_DIR, BASE_DIR, LOGGING_FORMAT, LOGGING_LEVEL, MODEL_FILENAME

# Configure logging
logging.basicConfig(level=LOGGING_LEVEL, format=LOGGING_FORMAT)

# Initialise MediaPipe Hands solution
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
hands = mp_hands.Hands(static_image_mode=True, min_detection_confidence=0.3)

# Initialise pygame mixer for playing sounds
pygame.mixer.init()

MAX_SENTENCE_LENGTH = 30  # Maximum allowed length of the sentence


def play_sound_for_prediction(prediction: str) -> None:
    """
    Play the sound corresponding to the predicted label.

    :param prediction: The label of the predicted sign (str).
    :return: None
    """
    sound_dir = os.path.join(BASE_DIR, 'audios')
    sound_file = os.path.join(sound_dir, f"{prediction}.wav")

    if os.path.exists(sound_file):
        Thread(target=pygame.mixer.Sound(sound_file).play, daemon=True).start()
    else:
        logging.warning(f"Sound file for '{prediction}' not found.")


def run_sign_language_interpreter() -> None:
    """
    Run the sign language interpreter using the webcam and the trained model.

    ":return: None
    """
    try:
        # Load the trained model
        with open(os.path.join(ARTIFACTS_DIR, MODEL_FILENAME), 'rb') as f:
            model_dict = pickle.load(f)
        model = model_dict['model']

        cap = cv2.VideoCapture(0)

        # Set the width and height
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 2304)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1536)

        window_name = "Sign Language Interpreter"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)

        prediction_history = deque(maxlen=5)  # Queue to store the last 5 predictions
        last_prediction = None
        sentence = ""
        error_message = ""

        while True:
            success, frame = cap.read()
            if not success:
                logging.error("Failed to capture frame from camera.")
                break
            # frame = cv2.flip(frame, 1)
            data_aux = []
            x_coords, y_coords, z_coords = [], [], []

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)
            if results.multi_hand_landmarks:
                error_message = ""
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style())
                    for lm in hand_landmarks.landmark:
                        x_coords.append(lm.x)
                        y_coords.append(lm.y)
                        z_coords.append(lm.z)
                    x_min, y_min, z_min = min(x_coords), min(y_coords), min(z_coords)
                    for lm in hand_landmarks.landmark:
                        data_aux.extend([lm.x - x_min, lm.y - y_min, lm.z - z_min])
                # Ensure the data matches the model's expected input size
                if len(data_aux) == model.n_features_in_:
                    prediction = model.predict([np.asarray(data_aux)])
                    predicted_label = prediction[0]

                    # Append the current prediction to the history
                    prediction_history.append(predicted_label)

                    # Check if the last 5 predictions are the same
                    if len(prediction_history) == 5 and all(
                            p == predicted_label for p in prediction_history) and predicted_label != last_prediction:
                        play_sound_for_prediction(predicted_label)
                        last_prediction = predicted_label
                        prediction_history.clear()

                    x1 = int(min(x_coords) * frame.shape[1]) - 10
                    y1 = int(min(y_coords) * frame.shape[0]) - 10
                    x2 = int(max(x_coords) * frame.shape[1]) + 10
                    y2 = int(max(y_coords) * frame.shape[0]) + 10

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), 2)
                    cv2.putText(frame, predicted_label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
                else:
                    logging.error(f"Feature count mismatch: expected {model.n_features_in_}, got {len(data_aux)}")
                    error_message = "Error: Feature count mismatch or Multiple hands detected"
                    prediction_history.clear()

            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):  # Space key pressed to confirm the letter
                if len(sentence) < MAX_SENTENCE_LENGTH:
                    if last_prediction:
                        sentence += last_prediction
                        last_prediction = None
                        prediction_history.clear()
                        cv2.waitKey(200)  # Add a 2-second delay before continuing
                else:
                    error_message = "Error: Sentence length limit reached"
            elif key == ord('s') or key == ord('S'):  # 's' key pressed to add a space to the sentence
                if len(sentence) < MAX_SENTENCE_LENGTH:
                    sentence += ' '
                    time.sleep(1)  # Add a slight delay after adding a space
                else:
                    error_message = "Error: Sentence length limit reached"
            elif key == ord('b') or key == ord('B'):  # Backspace key pressed to delete the last letter
                sentence = sentence[:-1]
                error_message = ""  # Clear the error message when the user deletes characters
            elif key == ord('q') or key == ord('Q'):  # Quit the program
                break

            # Display the sentence at the top of the screen
            cv2.putText(frame, sentence, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
            # Show a message to the user on how to quit the program
            quit_message = "Press 'q' to quit | 'space' to confirm | 's' to add space | 'b' to delete"
            cv2.putText(frame, quit_message, (50, frame.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0),
                        2)
            # Display the error message if the sentence length limit is reached
            if error_message:
                cv2.putText(frame, error_message, (50, frame.shape[0] - 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            cv2.imshow(window_name, frame)

            # Check if the window was closed unexpectedly
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                logging.info("Window closed. Exiting...")
                break

        cap.release()
        cv2.destroyAllWindows()
    except Exception as e:
        logging.error(f"An error occurred during inference: {e}")


if __name__ == "__main__":
    run_sign_language_interpreter()
