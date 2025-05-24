import socket, threading, json, io, time
from utils.screenshot import capture_screen
from PIL import Image
from PIL import ImageChops
import pyautogui
import zlib

pyautogui.FAILSAFE = False

IMG_PORT = 5001
CTRL_PORT = 5002


def start_image_server():
    s = socket.socket()
    s.bind(('0.0.0.0', IMG_PORT))
    s.listen(1)
    conn, _ = s.accept()

    screen_width, screen_height = pyautogui.size()
    info = json.dumps({
        "width": screen_width,
        "height": screen_height
    }).encode()
    conn.sendall(len(info).to_bytes(4, 'big') + info)

    prev_img = None

    while True:
        img = capture_screen()

        if prev_img is not None:
            diff = ImageChops.difference(img, prev_img)
            if not diff.getbbox():  # Если нет изменений
                time.sleep(0.066)
                continue

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=50)
        data = buf.getvalue()

        # Сжимаем данные
        compressed_data = zlib.compress(data)
        conn.sendall(len(compressed_data).to_bytes(4, 'big') + compressed_data)
        time.sleep(0.066)  # ~15 FPS


def start_control_server():
    s = socket.socket()
    s.bind(('0.0.0.0', CTRL_PORT))
    s.listen(1)
    conn, _ = s.accept()

    screen_width, screen_height = pyautogui.size()

    while True:
        try:
            # Считываем длину сообщения (4 байта)
            length_data = conn.recv(4)
            if not length_data:
                continue
            length = int.from_bytes(length_data, 'big')

            # Считываем само сообщение
            data = b""
            while len(data) < length:
                packet = conn.recv(length - len(data))
                if not packet:
                    break
                data += packet

            # Декодируем JSON
            cmd = json.loads(data.decode())

            x = cmd.get("x", 0)
            y = cmd.get("y", 0)
            client_w = cmd.get("width", screen_width)
            client_h = cmd.get("height", screen_height)
            scaled_x = int(x / client_w * screen_width)
            scaled_y = int(y / client_h * screen_height)

            match cmd["type"]:
                case "keypress":
                    pyautogui.keyDown(cmd["key"])
                case "keyrelease":
                    pyautogui.keyUp(cmd["key"])
                case "move":
                    pyautogui.moveTo(scaled_x, scaled_y)
                case "mousedown":
                    button = cmd.get("button", "left")
                    pyautogui.mouseDown(x=scaled_x, y=scaled_y, button=button)
                case "mouseup":
                    button = cmd.get("button", "left")
                    pyautogui.mouseUp(x=scaled_x, y=scaled_y, button=button)
                case "dblclick":
                    pyautogui.click(x=scaled_x, y=scaled_y, clicks=2, interval=0.1)
                case "scroll":
                    dy = cmd.get("dy", 0)
                    pyautogui.scroll(dy, x=scaled_x, y=scaled_y)
                case "keypress":
                    pyautogui.press(cmd["key"])

        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    threading.Thread(target=start_image_server, daemon=True).start()
    threading.Thread(target=start_control_server, daemon=True).start()

    while True:
        time.sleep(1)  # Основной поток остается активным