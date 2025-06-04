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
import sounddevice as sd
from tkinter import ttk, scrolledtext
from cryptography.fernet import Fernet

# Генерация ключа (выполнить один раз)
#key = Fernet.generate_key()
#print("Ваш секретный ключ:", key.decode())

class ServerGUI:
    def __init__(self):
        # Добавляем шифрование Fernet
        self.FERNET_KEY = b'eeoxN_0flIL_f1sC7UwVhcbeOqK7lWjFAO5iZIFC_yw='  # Вставьте сюда свой ключ

        self.window = tk.Tk()
        self.window.title("Сервер трансляции экрана")
        self.window.geometry("600x400")

        self.HOST = '0.0.0.0'  # Слушаем все доступные интерфейсы
        self.AUDIO_PORT = 5003  # Добавить новый порт для аудио
        self.audio_socket = None
        self.is_audio_running = False

        self.is_running = False
        self.server_thread = None
        self.conn = None
        self.socket = None

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

            self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.audio_socket.bind((self.HOST, self.AUDIO_PORT))
            self.audio_socket.listen(1)
            
            self.server_thread = threading.Thread(target=self.start_image_server, daemon=True)
            self.server_thread.start()

            audio_thread = threading.Thread(target=self.run_audio_server)
            audio_thread.daemon = True
            audio_thread.start()
            
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

    def run_audio_server(self):
        try:
            self.is_audio_running = True
            audio_conn, _ = self.audio_socket.accept()
            
            CHUNK = 1024
            CHANNELS = 2
            RATE = 44100

            # Найдем виртуальный кабель среди устройств
            devices = sd.query_devices()
            cable_device = None
            for i, dev in enumerate(devices):
                if 'CABLE Output' in dev['name']:
                    cable_device = i
                    self.log(f"Найден VB-Cable: {dev['name']}")
                    break
            
            if self.fernet:
                self.log(f"Аудио: защищенное соединение установлено с {_[0]}")

            if cable_device is None:
                self.log("VB-Cable не найден. Установите VB-Cable для захвата системного звука.")
                return

            def audio_callback(indata, frames, time, status):
                try:
                    if self.is_running:
                        audio_data = (indata * 32767).astype(np.int16).tobytes()
                        
                        # Шифрование аудио данных
                        encrypted_audio = self.fernet.encrypt(audio_data)
                        
                        # Отправка размера + зашифрованных данных
                        audio_conn.sendall(len(encrypted_audio).to_bytes(4, 'big') + encrypted_audio)
                except:
                    pass

            # Используем VB-Cable как устройство ввода
            with sd.InputStream(
                channels=CHANNELS,
                samplerate=RATE,
                blocksize=CHUNK,
                callback=audio_callback,
                device=cable_device,
                latency='low'
            ) as stream:
                self.log("Аудио поток запущен")
                while self.is_running:
                    sd.sleep(100)
            
            audio_conn.close()
            
        except Exception as e:
            self.log(f"Ошибка аудио сервера: {str(e)}")

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

            if self.fernet:
                self.log(f"Видео: защищенное соединение установлено с {addr[0]}")
            
            info = json.dumps({"width": screen_width, "height": screen_height}).encode()
            self.conn.sendall(len(info).to_bytes(4, 'big') + info)

            prev_frame = None
            last_sent = time.time()
            FORCE_SEND_INTERVAL = 0.3
            QUALITY = 50

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

                    # Шифрование данных перед отправкой
                    encrypted_data = self.fernet.encrypt(data)
                    
                    try:
                        # Отправляем размер зашифрованных данных
                        self.conn.sendall(len(encrypted_data).to_bytes(4, 'big'))
                        # Отправляем сами зашифрованные данные
                        self.conn.sendall(encrypted_data)
                        prev_frame = current_frame.copy()
                    except Exception as e:
                        self.log(f"Ошибка отправки: {str(e)}")
                        break

                time.sleep(0.016)

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

                if self.fernet:
                    self.log(f"Управление: защищенное соединение установлено с {addr[0]}")
                
                while self.is_running:
                    # Получаем размер зашифрованных данных
                    length_data = conn.recv(4)
                    if not length_data: break
                    length = int.from_bytes(length_data, 'big')
                    
                    # Получаем зашифрованные данные
                    encrypted_data = b""
                    while len(encrypted_data) < length:
                        packet = conn.recv(length - len(encrypted_data))
                        if not packet: break
                        encrypted_data += packet
                    
                    try:
                        # Расшифровываем данные
                        decrypted_data = self.fernet.decrypt(encrypted_data)
                        cmd = json.loads(decrypted_data.decode())
                        self.handle_command(cmd)
                    except Exception as e:
                        self.log(f"Ошибка расшифровки команды: {str(e)}")

            except Exception as e:
                self.log(f"Ошибка управления: {str(e)}")
            finally:
                conn.close()
        s.close()

if __name__ == "__main__":
    ServerGUI()