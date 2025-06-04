import socket
import threading
import json
import io
import time
import cv2
import math
import keyboard
import pyaudio
import numpy as np
from PIL import Image
import zlib
import tkinter as tk
from tkinter import ttk, scrolledtext
from cryptography.fernet import Fernet

class ClientGUI:
    def __init__(self):
        # Добавляем шифрование Fernet
        self.FERNET_KEY = b'eeoxN_0flIL_f1sC7UwVhcbeOqK7lWjFAO5iZIFC_yw='  # Тот же ключ, что и на сервере

        self.window = tk.Tk()
        self.window.title("Клиент трансляции экрана")
        self.window.geometry("600x400")

        self.AUDIO_PORT = 5003
        self.audio_sock = None
        self.is_audio_connected = False

        self.is_connected = False
        self.image_thread = None
        self.sock = None
        self.control_sock = None  # Добавить
        self.mouse_state = {"last_position": [0, 0]}  # Добавить

        self.keyboard_listener = None  # Добавить

        self.current_width = 0  # Добавить
        self.current_height = 0  # Добавить

        # GUI элементы
        self.create_widgets()

        try:
            self.fernet = Fernet(self.FERNET_KEY)
            self.log("Шифрование Fernet успешно инициализировано")
        except Exception as e:
            self.log(f"Ошибка инициализации шифрования: {str(e)}")
            self.fernet = None

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
            self.log("Видео соединение установлено")
            if self.fernet:
                self.log("Видео: защищенное соединение активировано")

            self.audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.audio_sock.connect((self.ip_entry.get(), self.AUDIO_PORT))
            self.log("Управление: соединение установлено")
            if self.fernet:
                self.log("Управление: защищенное соединение активировано")

            audio_thread = threading.Thread(target=self.receive_audio)
            audio_thread.daemon = True
            audio_thread.start()
            self.log("Аудио соединение установлено")
            if self.fernet:
                self.log("Аудио: защищенное соединение активировано")

            self.keyboard_listener = threading.Thread(target=self.setup_keyboard_handling, daemon=True)
            self.keyboard_listener.start()

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
    
    def setup_keyboard_handling(self):
        """Инициализация обработки клавиатуры"""
        keyboard.on_press(self.on_key_press)
        keyboard.on_release(self.on_key_release)
        keyboard.wait()

    def on_key_press(self, event):
        """Обработчик нажатия клавиш"""
        if self.is_connected and event.event_type == keyboard.KEY_DOWN:
            self.send_control_command({
                "type": "keypress",
                "key": event.name
            })

    def on_key_release(self, event):
        """Обработчик отпускания клавиш"""
        if self.is_connected and event.event_type == keyboard.KEY_UP:
            self.send_control_command({
                "type": "keyrelease",
                "key": event.name
            })

    def disconnect(self):
        """Отключение от сервера"""
        self.is_connected = False
        if self.keyboard_listener:
            keyboard.unhook_all()
            self.keyboard_listener = None
        if self.sock:
            self.sock.close()
        if self.audio_sock:
            self.audio_sock.close()
        self.is_audio_connected = False
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

    def receive_audio(self):
        try:
            self.is_audio_connected = True
            
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 2
            RATE = 44100
            
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT,
                          channels=CHANNELS,
                          rate=RATE,
                          output=True,
                          frames_per_buffer=CHUNK)
            
            while self.is_connected:
                try:
                    # Получаем размер данных
                    size_data = self.audio_sock.recv(4)
                    if not size_data:
                        break
                    size = int.from_bytes(size_data, 'big')
                    
                    # Получаем зашифрованные данные
                    encrypted_audio = b""
                    while len(encrypted_audio) < size:
                        packet = self.audio_sock.recv(size - len(encrypted_audio))
                        if not packet:
                            break
                        encrypted_audio += packet
                    
                    # Расшифровка аудио
                    try:
                        audio_data = self.fernet.decrypt(encrypted_audio)
                    except:
                        self.log("Ошибка расшифровки аудио")
                        continue
                    
                    stream.write(audio_data)
                except:
                    break
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            self.audio_sock.close()
            self.is_audio_connected = False
            
        except Exception as e:
            self.log(f"Ошибка аудио потока: {str(e)}")
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
            #cv2.setWindowProperty("Remote Screen", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

            while self.is_connected:
                # Получаем размер данных
                size_data = self.sock.recv(4)
                if not size_data:
                    break
                size = int.from_bytes(size_data, 'big')
                
                # Получаем зашифрованные данные
                encrypted_data = b""
                while len(encrypted_data) < size:
                    packet = self.sock.recv(size - len(encrypted_data))
                    if not packet:
                        break
                    encrypted_data += packet
                
                # Расшифровка данных
                try:
                    compressed_data = self.fernet.decrypt(encrypted_data)
                except:
                    self.log("Ошибка расшифровки видеоданных")
                    continue

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
        data = json.dumps(cmd).encode()
        
        # Шифрование команды перед отправкой
        encrypted_data = self.fernet.encrypt(data)
        
        try:
            # Отправляем размер зашифрованных данных
            self.control_sock.sendall(len(encrypted_data).to_bytes(4, 'big'))
            # Отправляем зашифрованные данные
            self.control_sock.sendall(encrypted_data)
        except Exception as e:
            self.log(f"Ошибка отправки команды: {str(e)}")

    def mouse_callback(self, event, x, y, flags, param):
        """Обработчик событий мыши"""
        MIN_MOVE_DISTANCE = 5
        last_position = self.mouse_state["last_position"]

        try:
            if event == cv2.EVENT_MOUSEMOVE:
                # Проверяем, переместилась ли мышь на достаточное расстояние
                if math.hypot(x - last_position[0], y - last_position[1]) > MIN_MOVE_DISTANCE:
                    cmd = {
                        "type": "move",
                        "x": x,
                        "y": y,
                        "width": self.current_width,
                        "height": self.current_height,
                        "drag": self.mouse_state.get("dragging", False)  # Указываем, идет ли перетаскивание
                    }
                    self.send_control_command(cmd)
                    self.mouse_state["last_position"] = [x, y]

            elif event == cv2.EVENT_LBUTTONDOWN:
                # Устанавливаем флаг перетаскивания
                self.mouse_state["dragging"] = True
                self.send_control_command({
                    "type": "mousedown",
                    "button": "left",
                    "x": x,
                    "y": y
                })

            elif event == cv2.EVENT_LBUTTONUP:
                # Сбрасываем флаг перетаскивания
                self.mouse_state["dragging"] = False
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