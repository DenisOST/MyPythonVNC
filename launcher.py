import tkinter as tk
from tkinter import ttk
from client import ClientGUI
from server import ServerGUI

class Launcher:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("VNC Launcher")
        self.window.geometry("300x200")
        
        # Центрируем окно
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = (screen_width - 300) // 2
        y = (screen_height - 200) // 2
        self.window.geometry(f"300x200+{x}+{y}")
        
        self.server_window = None
        self.client_window = None
        self.is_closing = False
        
        self.create_widgets()
        
    def create_widgets(self):
        # Создаем основной контейнер
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        ttk.Label(
            main_frame, 
            text="Выберите режим работы", 
            font=('Helvetica', 12, 'bold')
        ).pack(pady=20)
        
        # Кнопка запуска сервера
        ttk.Button(
            main_frame,
            text="Запустить как сервер",
            command=self.start_server,
            width=25
        ).pack(pady=10)
        
        # Кнопка запуска клиента
        ttk.Button(
            main_frame,
            text="Запустить как клиент",
            command=self.start_client,
            width=25
        ).pack(pady=10)
        
    def start_server(self):
        self.window.withdraw()  # Скрываем окно лаунчера
        self.server_window = ServerGUI()
        self.server_window.window.protocol("WM_DELETE_WINDOW", self.on_server_close)
        
    def start_client(self):
        self.window.withdraw()  # Скрываем окно лаунчера
        self.client_window = ClientGUI()
        self.client_window.window.protocol("WM_DELETE_WINDOW", self.on_client_close)
    
    def on_server_close(self):
        """Обработчик закрытия окна сервера"""
        if self.is_closing:
            return
            
        self.is_closing = True
        
        try:
            if hasattr(self.server_window, 'on_close'):
                self.server_window.on_close()
        except:
            pass
            
        try:
            self.window.quit()
        except:
            pass
            
        self.window.destroy()
    
    def on_client_close(self):
        """Обработчик закрытия окна клиента"""
        if self.is_closing:
            return
            
        self.is_closing = True
        
        try:
            if hasattr(self.client_window, 'on_close'):
                self.client_window.on_close()
        except:
            pass
            
        try:
            self.window.quit()
        except:
            pass
            
        self.window.destroy()

if __name__ == "__main__":
    app = Launcher()
    app.window.mainloop()