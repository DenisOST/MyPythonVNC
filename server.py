import socket
import threading
import json
import io
import time
import mss
import numpy as np
from PIL import Image
import zlib
import tkinter as tk
import pyautogui
from tkinter import ttk, scrolledtext

class ServerGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Сервер трансляции экрана")
        self.window.geometry("600x400")

        self.is_running = False
        self.server_thread = None
        self.conn = None
        self.socket = None

        self.create_widgets()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        self.window.mainloop()

    def create_widgets(self):
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.start_btn = ttk.Button(
            control_frame,
            text="Запустить сервер",
            command=self.toggle_server
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(control_frame, text="Статус: Остановлен", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.log_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log("Сервер готов к запуску")

    def toggle_server(self):
        if self.is_running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        try:
            self.is_running = True
            self.start_btn.config(text="Остановить сервер")
            self.status_label.config(text="Статус: Работает", foreground="green")
            
            self.server_thread = threading.Thread(target=self.start_image_server, daemon=True)
            self.server_thread.start()
            
            self.log("Сервер запущен на порту 5001")

        except Exception as e:
            self.log(f"Ошибка запуска: {str(e)}")

    def stop_server(self):
        self.is_running = False
        if self.conn:
            self.conn.close()
        if self.socket:
            self.socket.close()
        self.start_btn.config(text="Запустить сервер")
        self.status_label.config(text="Статус: Остановлен", foreground="red")
        self.log("Сервер остановлен")

    def log(self, message):
        self.log_area.insert(tk.END, f"[{time.ctime()}] {message}\n")
        self.log_area.see(tk.END)

    def on_close(self):
        self.stop_server()
        self.window.destroy()

    def start_image_server(self):
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.socket.bind(('0.0.0.0', 5001))
        self.socket.listen(1)
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screen_width = monitor["width"]
            screen_height = monitor["height"]
        
        try:
            self.conn, addr = self.socket.accept()
            self.log(f"Клиент подключен: {addr[0]}")
            
            info = json.dumps({"width": screen_width, "height": screen_height}).encode()
            self.conn.sendall(len(info).to_bytes(4, 'big') + info)

            prev_frame = None
            last_sent = time.time()
            FORCE_SEND_INTERVAL = 0.3
            QUALITY = 40

            # Запуск сервера управления в отдельном потоке
            control_thread = threading.Thread(target=self.run_control_server, daemon=True)
            control_thread.start()

            while self.is_running:
                img = self.capture_screen()  # Получаем PIL Image в RGB
                current_frame = np.array(img)

                send_frame = False
                if prev_frame is not None:
                    has_changes = not np.array_equal(current_frame, prev_frame)
                else:
                    has_changes = True

                if (time.time() - last_sent) > FORCE_SEND_INTERVAL:
                    send_frame = True
                    last_sent = time.time()

                if has_changes or send_frame:
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=QUALITY)
                    data = zlib.compress(buf.getvalue())
                    
                    try:
                        self.conn.sendall(len(data).to_bytes(4, 'big') + data)
                        prev_frame = current_frame.copy()
                    except Exception as e:
                        self.log(f"Ошибка отправки: {str(e)}")
                        break

                time.sleep(0.033)

        except Exception as e:
            self.log(f"Ошибка соединения: {str(e)}")
        finally:
            self.socket.close()
            self.log("Соединение закрыто")

    def capture_screen(self):
        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
            return Image.frombytes(
                'RGB',
                (sct_img.width, sct_img.height),
                sct_img.rgb
            )
        
    def handle_command(self, cmd):
        """Обработка команд управления"""
        try:
            screen_width, screen_height = pyautogui.size()
            client_w = cmd.get("width", screen_width)
            client_h = cmd.get("height", screen_height)
            
            # Масштабирование координат
            def scale_x(x): return int(x / client_w * screen_width)
            def scale_y(y): return int(y / client_h * screen_height)

            match cmd["type"]:
                case "move":
                    pyautogui.moveTo(scale_x(cmd["x"]), scale_y(cmd["y"]))
                case "mousedown":
                    button = cmd.get("button", "left")
                    pyautogui.mouseDown(button=button)
                case "mouseup":
                    button = cmd.get("button", "left")
                    pyautogui.mouseUp(button=button)
                case "dblclick":
                    pyautogui.click(clicks=2, interval=0.1)
                case "scroll":
                    dy = cmd.get("dy", 0)
                    pyautogui.scroll(dy)
                case "keypress":
                    try:
                        pyautogui.keyDown(cmd["key"])
                    except Exception as e:
                        self.log(f"Ошибка нажатия клавиши {cmd['key']}: {str(e)}")
                    
                case "keyrelease":
                    try:
                        pyautogui.keyUp(cmd["key"])
                    except Exception as e:
                        self.log(f"Ошибка отпускания клавиши {cmd['key']}: {str(e)}")
                case _:
                    self.log(f"Неизвестная команда: {cmd['type']}")

        except Exception as e:
            self.log(f"Ошибка выполнения команды: {str(e)}")
    
    def run_control_server(self):
        """Сервер для управления мышью/клавиатурой"""
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', 5002))
        s.listen(1)
        
        while self.is_running:
            try:
                conn, addr = s.accept()
                self.log(f"Подключение управления: {addr[0]}")
                
                while self.is_running:
                    length_data = conn.recv(4)
                    if not length_data: break
                    length = int.from_bytes(length_data, 'big')
                    
                    data = b""
                    while len(data) < length:
                        packet = conn.recv(length - len(data))
                        if not packet: break
                        data += packet
                    
                    cmd = json.loads(data.decode())
                    self.handle_command(cmd)

            except Exception as e:
                self.log(f"Ошибка управления: {str(e)}")
            finally:
                conn.close()
        s.close()

if __name__ == "__main__":
    ServerGUI()