import socket
import threading
import json
import io
import time
import cv2
import math
import numpy as np
from PIL import Image
import zlib
import tkinter as tk
from tkinter import ttk, scrolledtext

class ClientGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Клиент трансляции экрана")
        self.window.geometry("600x400")

        self.is_connected = False
        self.image_thread = None
        self.sock = None
        self.control_sock = None  # Добавить
        self.mouse_state = {"last_position": [0, 0]}  # Добавить

        self.current_width = 0  # Добавить
        self.current_height = 0  # Добавить

        # GUI элементы
        self.create_widgets()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        self.window.mainloop()

    def create_widgets(self):
        """Создание элементов интерфейса"""
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Панель подключения
        conn_frame = ttk.Frame(main_frame)
        conn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(conn_frame, text="IP сервера:").pack(side=tk.LEFT)
        self.ip_entry = ttk.Entry(conn_frame, width=20)
        self.ip_entry.pack(side=tk.LEFT, padx=5)
        self.ip_entry.insert(0, "192.168.206.128")

        self.connect_btn = ttk.Button(
            conn_frame,
            text="Подключиться",
            command=self.toggle_connection
        )
        self.connect_btn.pack(side=tk.LEFT)

        # Лог событий
        self.log_area = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log("Готов к подключению")

    def toggle_connection(self):
        """Обработчик подключения/отключения"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        """Подключение к серверу"""
        try:
            self.sock = socket.socket()
            self.sock.connect((self.ip_entry.get(), 5001))
            self.is_connected = True
            self.connect_btn.config(text="Отключиться")
            
            self.image_thread = threading.Thread(target=self.receive_images, daemon=True)
            self.image_thread.start()

            self.control_sock = socket.socket()
            self.control_sock.connect((self.ip_entry.get(), 5002))
            
            # Запуск обработки мыши
            threading.Thread(target=self.setup_mouse_handling, daemon=True).start()
            
            self.log("Успешное подключение")

        except Exception as e:
            self.log(f"Ошибка подключения: {str(e)}")

    def setup_mouse_handling(self):
        """Инициализация обработки событий мыши"""
        cv2.namedWindow("Remote Screen")
        cv2.setMouseCallback("Remote Screen", self.mouse_callback)

    def disconnect(self):
        """Отключение от сервера"""
        self.is_connected = False
        if self.sock:
            self.sock.close()
        self.connect_btn.config(text="Подключиться")
        cv2.destroyAllWindows()
        self.log("Соединение разорвано")

    def log(self, message):
        """Логирование сообщений"""
        self.log_area.insert(tk.END, f"[{time.ctime()}] {message}\n")
        self.log_area.see(tk.END)

    def on_close(self):
        """Обработчик закрытия окна"""
        self.disconnect()
        self.window.destroy()

    # Ваша оригинальная функция с небольшими модификациями
    def receive_images(self):
        try:
            # Получаем информацию о разрешении
            info_size = int.from_bytes(self.sock.recv(4), 'big')
            info_data = self.sock.recv(info_size)
            screen_info = json.loads(info_data.decode())

            # После получения screen_info добавить:
            self.current_width = screen_info['width']
            self.current_height = screen_info['height']

            # Настройка окна OpenCV
            cv2.namedWindow("Remote Screen", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty("Remote Screen", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

            while self.is_connected:
                # Получаем размер данных
                size_data = self.sock.recv(4)
                if not size_data:
                    break
                size = int.from_bytes(size_data, 'big')
                
                # Получаем сжатые данные
                compressed_data = b""
                while len(compressed_data) < size:
                    packet = self.sock.recv(size - len(compressed_data))
                    if not packet:
                        break
                    compressed_data += packet

                # Обработка изображения
                decompressed = zlib.decompress(compressed_data)
                img = Image.open(io.BytesIO(decompressed))
                frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                cv2.imshow("Remote Screen", frame)

                if cv2.waitKey(1) == 27:  # ESC для выхода
                    break

        except Exception as e:
            self.log(f"Ошибка видеопотока: {str(e)}")
        finally:
            self.disconnect()

    def send_control_command(self, cmd):
        """Отправка команды управления"""
        try:
            data = json.dumps(cmd).encode()
            self.control_sock.sendall(len(data).to_bytes(4, 'big') + data)
        except Exception as e:
            self.log(f"Ошибка отправки команды: {str(e)}")
            
    def mouse_callback(self, event, x, y, flags, param):
            """Обработчик событий мыши"""
            MIN_MOVE_DISTANCE = 5
            last_position = self.mouse_state["last_position"]

            try:
                if event == cv2.EVENT_MOUSEMOVE:
                    if math.hypot(x - last_position[0], y - last_position[1]) > MIN_MOVE_DISTANCE:
                        cmd = {
                            "type": "move",
                            "x": x,
                            "y": y,
                            "width": self.current_width,
                            "height": self.current_height
                        }
                        self.send_control_command(cmd)
                        self.mouse_state["last_position"] = [x, y]

                elif event == cv2.EVENT_LBUTTONDOWN:
                    self.send_control_command({
                        "type": "mousedown",
                        "button": "left",
                        "x": x,
                        "y": y
                    })

                elif event == cv2.EVENT_LBUTTONUP:
                    self.send_control_command({
                        "type": "mouseup",
                        "button": "left",
                        "x": x,
                        "y": y
                    })

                elif event == cv2.EVENT_RBUTTONDOWN:
                    self.send_control_command({"type": "mousedown", "x": x, "y": y, "button": "right"})

                elif event == cv2.EVENT_RBUTTONUP:
                    self.send_control_command({"type": "mouseup", "x": x, "y": y, "button": "right"})

                elif event == cv2.EVENT_MBUTTONDOWN:
                    self.send_control_command({"type": "mousedown", "x": x, "y": y, "button": "middle"})

                elif event == cv2.EVENT_MBUTTONUP:
                    self.send_control_command({"type": "mouseup", "x": x, "y": y, "button": "middle"})

                elif event == cv2.EVENT_MOUSEWHEEL:
                    dy = flags >> 16
                    self.send_control_command({"type": "scroll", "x": x, "y": y, "dy": dy})

            except Exception as e:
                self.log(f"Ошибка мыши: {str(e)}")

if __name__ == "__main__":
    ClientGUI()