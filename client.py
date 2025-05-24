import socket, threading, struct, json, io
from PIL import Image
from pynput.keyboard import Listener as KeyListener
import pyautogui as pag
import keyboard  # Библиотека для обработки клавиш
import zlib

screen_width, screen_height = pag.size()

SERVER_IP = '192.168.206.128'
IMG_PORT = 5001
CTRL_PORT = 5002

ctrl_sock = socket.socket()
ctrl_sock.connect((SERVER_IP, CTRL_PORT))

# Добавляем глобальный словарь для отслеживания состояния клавиш
pressed_keys = set()

# Функция для обработки нажатий клавиш
def send_command(cmd):
    data = json.dumps(cmd).encode()
    length = len(data).to_bytes(4, 'big')  # 4 байта для длины сообщения
    ctrl_sock.sendall(length + data)  # Отправляем длину + данные

def handle_keyboard():
    # Обработка нажатий клавиш
    def on_press(event):
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
    # Вставка внутрь функции receive_images

    last_click_time = [0]
    is_dragging = [False]

    def mouse_callback(event, x, y, flags, param):
        import time

        if event == cv2.EVENT_MOUSEMOVE:
            if is_dragging[0]:
                send_command({
                    "type": "move",
                    "x": x,
                    "y": y,
                    "drag": True
                })
            else:
                send_command({
                    "type": "move",
                    "x": x,
                    "y": y
                })

        elif event == cv2.EVENT_LBUTTONDOWN:
            now = time.time()
            if now - last_click_time[0] < 0.3:  # Двойной клик
                send_command({"type": "dblclick", "x": x, "y": y})
            else:
                send_command({"type": "mousedown", "x": x, "y": y, "button": "left"})
                is_dragging[0] = True
            last_click_time[0] = now

        elif event == cv2.EVENT_LBUTTONUP:
            send_command({"type": "mouseup", "x": x, "y": y, "button": "left"})
            is_dragging[0] = False

        elif event == cv2.EVENT_RBUTTONDOWN:  # ПКМ нажата
            send_command({"type": "mousedown", "x": x, "y": y, "button": "right"})

        elif event == cv2.EVENT_RBUTTONUP:  # ПКМ отпущена
            send_command({"type": "mouseup", "x": x, "y": y, "button": "right"})

        elif event == cv2.EVENT_MOUSEWHEEL:  # Скролл мыши
            dy = flags >> 16  # Извлекаем направление скролла
            send_command({"type": "scroll", "x": x, "y": y, "dy": dy})


    cv2.setMouseCallback(window_name, mouse_callback)

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