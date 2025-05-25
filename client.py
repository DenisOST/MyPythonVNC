import socket, threading, struct, json, io
from PIL import Image
from pynput.keyboard import Listener as KeyListener
import pyautogui as pag
import keyboard  # Библиотека для обработки клавиш
import zlib
import time
import math

screen_width, screen_height = pag.size()

SERVER_IP = '192.168.206.128'
IMG_PORT = 5001
CTRL_PORT = 5002

ctrl_sock = socket.socket()
ctrl_sock.connect((SERVER_IP, CTRL_PORT))

# Функция для обработки нажатий клавиш
def send_command(cmd):
    data = json.dumps(cmd).encode()
    length = len(data).to_bytes(4, 'big')  # 4 байта для длины сообщения
    ctrl_sock.sendall(length + data)  # Отправляем длину + данные

# Добавляем глобальный словарь для отслеживания времени последнего нажатия клавиш
key_timestamps = {}

# Минимальный интервал между обработкой повторных нажатий одной клавиши (в секундах)
KEY_PRESS_INTERVAL = 0.1

def handle_keyboard():
    # Обработка нажатий клавиш
    def on_press(event):
        current_time = time.time()
        last_time = key_timestamps.get(event.name, 0)

        # Проверяем, прошло ли достаточно времени с последнего нажатия
        if current_time - last_time > KEY_PRESS_INTERVAL:
            key_timestamps[event.name] = current_time
            send_command({"type": "keypress", "key": event.name})

    # Обработка отпусканий клавиш
    def on_release(event):
        send_command({"type": "keyrelease", "key": event.name})

    # Регистрация обработчиков
    keyboard.on_press(on_press)
    keyboard.on_release(on_release)

    # Блокируем поток, чтобы слушатель оставался активным
    keyboard.wait()

# Запуск обработки клавиатуры в отдельном потоке
threading.Thread(target=handle_keyboard, daemon=True).start()

def receive_images():
    import cv2
    import numpy as np

    s = socket.socket()
    s.connect((SERVER_IP, IMG_PORT))

    # Получаем размер экрана
    info_size = int.from_bytes(s.recv(4), 'big')
    info_data = s.recv(info_size)
    screen_info = json.loads(info_data.decode())
    remote_w = screen_info['width']
    remote_h = screen_info['height']

    window_name = "Remote Screen"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    is_fullscreen = [True]

    # 🖱️ Обработка событий мыши в окне
    last_click_time = [0]
    is_dragging = [False]

    # Создаём словарь для хранения состояния
    mouse_state = {"last_position": [0, 0]}

    def mouse_callback(event, x, y, flags, param):

        MIN_MOVE_DISTANCE = 5
        last_position = param["last_position"]

        if event == cv2.EVENT_MOUSEMOVE:
            # Проверяем, переместилась ли мышь на достаточное расстояние
            if math.hypot(x - last_position[0], y - last_position[1]) > MIN_MOVE_DISTANCE:
                if is_dragging[0]:  # Если ЛКМ зажата
                    send_command({
                        "type": "move",
                        "x": x,
                        "y": y,
                        "drag": True  # Указываем, что это перетаскивание
                    })
                else:
                    send_command({
                        "type": "move",
                        "x": x,
                        "y": y
                    })
                param["last_position"] = [x, y]

        elif event == cv2.EVENT_LBUTTONDOWN:
            now = time.time()
            if now - last_click_time[0] < 0.7:  # Двойной клик
                send_command({"type": "dblclick", "x": x, "y": y})
                last_click_time[0] = 0  # Сбрасываем таймер для предотвращения тройного клика
            else:
                send_command({"type": "mousedown", "x": x, "y": y, "button": "left"})
                is_dragging[0] = True  # Устанавливаем флаг перетаскивания
            last_click_time[0] = now

        elif event == cv2.EVENT_LBUTTONUP:
            # Добавляем небольшую задержку перед отправкой команды отпускания
            time.sleep(0.05)
            send_command({"type": "mouseup", "x": x, "y": y, "button": "left"})
            is_dragging[0] = False  # Сбрасываем флаг перетаскивания

        elif event == cv2.EVENT_RBUTTONDOWN:
            send_command({"type": "mousedown", "x": x, "y": y, "button": "right"})

        elif event == cv2.EVENT_RBUTTONUP:
            send_command({"type": "mouseup", "x": x, "y": y, "button": "right"})

        elif event == cv2.EVENT_MBUTTONDOWN:
            send_command({"type": "mousedown", "x": x, "y": y, "button": "middle"})

        elif event == cv2.EVENT_MBUTTONUP:
            send_command({"type": "mouseup", "x": x, "y": y, "button": "middle"})

        elif event == cv2.EVENT_MOUSEWHEEL:
            dy = flags >> 16
            send_command({"type": "scroll", "x": x, "y": y, "dy": dy})

    # Передаём mouse_state в качестве параметра
    cv2.setMouseCallback(window_name, mouse_callback, mouse_state)

    while True:
        try:
            size_data = s.recv(4)
            if not size_data:
                continue
            size = int.from_bytes(size_data, 'big')
            buf = b""
            while len(buf) < size:
                packet = s.recv(size - len(buf))
                if not packet:
                    break
                buf += packet

            # Распаковываем данные
            decompressed_data = zlib.decompress(buf)

            img = Image.open(io.BytesIO(decompressed_data))
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            cv2.imshow(window_name, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # Esc для выхода
                break

        except Exception as e:
            print("Image receive error:", e)
            break

    s.close()
    cv2.destroyAllWindows()

# Запуск потоков
threading.Thread(target=receive_images).start()
threading.Thread(target=handle_keyboard, daemon=True).start()