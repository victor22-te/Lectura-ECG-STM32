"""
Autor:Victor,Joel y Uriel 
Generado para proyecto STM32F401 + AD8232
"""

import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports
import threading
import collections
import time
import numpy as np
import winsound
from datetime import datetime
from scipy import signal

class ECGMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("❤ Monitor de ECG AD8232")
        self.root.configure(bg='#1a1a2e')
        self.root.geometry("1200x700")
        self.root.minsize(900, 600)
        
        # Variables de estado
        self.serial_port = None
        self.is_running = False
        self.data_buffer = collections.deque(maxlen=500)      # Datos filtrados
        self.raw_buffer = collections.deque(maxlen=500)       # Datos sin filtrar
        self.time_buffer = collections.deque(maxlen=500)
        self.bpm_history = collections.deque(maxlen=10)
        self.last_beat_time = 0
        self.beat_times = collections.deque(maxlen=20)
        self.current_bpm = 0
        self.leads_off = False
        self.beat_detected = False
        self.beat_animation_counter = 0
        
        # Parámetros de detección de latidos
        self.threshold = 2800  # Umbral para detección de pico R
        self.min_beat_interval = 0.3  # Mínimo 0.3 segundos entre latidos (200 BPM máx)
        self.last_peak_value = 0
        self.rising = False
        
        # ========== CONFIGURACIÓN DE FILTROS DIGITALES ==========
        self.fs = 250  # Frecuencia de muestreo (Hz)
        
        # Filtro Pasa-Bajas (elimina ruido de alta frecuencia)
        # Frecuencia de corte: 35Hz - preserva ondas P, QRS, T
        self.lp_cutoff = 35
        self.lp_order = 4
        self.lp_b, self.lp_a = signal.butter(self.lp_order, 
                                              self.lp_cutoff / (self.fs / 2), 
                                              btype='low')
        self.lp_zi = signal.lfilter_zi(self.lp_b, self.lp_a) * 2048
        
        # Filtro Pasa-Altas (elimina deriva de línea base)
        # Frecuencia de corte: 0.5Hz
        self.hp_cutoff = 0.5
        self.hp_order = 4
        self.hp_b, self.hp_a = signal.butter(self.hp_order, 
                                              self.hp_cutoff / (self.fs / 2), 
                                              btype='high')
        self.hp_zi = signal.lfilter_zi(self.hp_b, self.hp_a) * 0
        
        # Filtro Notch para eliminar interferencia de red (60Hz)
        self.notch_freq = 60
        self.notch_q = 30  # Factor de calidad
        self.notch_b, self.notch_a = signal.iirnotch(self.notch_freq / (self.fs / 2), 
                                                       self.notch_q)
        self.notch_zi = signal.lfilter_zi(self.notch_b, self.notch_a) * 2048
        
        # Control de filtrado
        self.filter_enabled = True
        
        # Configurar estilos
        self.setup_styles()
        
        # Crear interfaz
        self.create_widgets()
        
        # Iniciar actualización de gráfica
        self.update_plot()
        
    def setup_styles(self):
        """Configurar estilos visuales"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores del tema
        self.colors = {
            'bg_dark': '#1a1a2e',
            'bg_medium': '#16213e',
            'bg_light': '#0f3460',
            'accent': '#e94560',
            'accent_light': '#ff6b6b',
            'text': '#ffffff',
            'text_dim': '#a0a0a0',
            'success': '#4ecca3',
            'warning': '#ffc107',
            'ecg_line': '#00ff88',
            'grid': '#2a2a4e'
        }
        
        style.configure('TButton',
                       background=self.colors['accent'],
                       foreground='white',
                       font=('Segoe UI', 11, 'bold'),
                       padding=10)
        
        style.configure('TLabel',
                       background=self.colors['bg_dark'],
                       foreground=self.colors['text'],
                       font=('Segoe UI', 11))
        
        style.configure('TCombobox',
                       fieldbackground=self.colors['bg_medium'],
                       background=self.colors['bg_light'],
                       foreground='black',
                       font=('Segoe UI', 10))
        
    def create_widgets(self):
        """Crear todos los widgets de la interfaz"""
        
        # Frame principal
        main_frame = tk.Frame(self.root, bg=self.colors['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # ==== ENCABEZADO ====
        header_frame = tk.Frame(main_frame, bg=self.colors['bg_dark'])
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Título
        title_label = tk.Label(header_frame, 
                              text="❤ Monitor de ECG",
                              font=('Segoe UI', 28, 'bold'),
                              bg=self.colors['bg_dark'],
                              fg=self.colors['accent'])
        title_label.pack(side=tk.LEFT)
        
        # Subtítulo
        subtitle_label = tk.Label(header_frame,
                                 text="  STM32F401 + AD8232",
                                 font=('Segoe UI', 14),
                                 bg=self.colors['bg_dark'],
                                 fg=self.colors['text_dim'])
        subtitle_label.pack(side=tk.LEFT, padx=10)
        
        # ==== PANEL DE CONTROL ====
        control_frame = tk.Frame(main_frame, bg=self.colors['bg_medium'], 
                                relief=tk.FLAT, bd=0)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        control_inner = tk.Frame(control_frame, bg=self.colors['bg_medium'])
        control_inner.pack(padx=15, pady=15)
        
        # Puerto COM
        port_label = tk.Label(control_inner, text="Puerto COM:",
                             font=('Segoe UI', 11, 'bold'),
                             bg=self.colors['bg_medium'],
                             fg=self.colors['text'])
        port_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(control_inner, textvariable=self.port_var,
                                       width=15, state='readonly')
        self.port_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.refresh_ports()
        
        # Botón refrescar puertos
        refresh_btn = tk.Button(control_inner, text="🔄",
                               font=('Segoe UI', 12),
                               bg=self.colors['bg_light'],
                               fg=self.colors['text'],
                               relief=tk.FLAT,
                               cursor='hand2',
                               command=self.refresh_ports)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 20))
        
        # Botón conectar/desconectar
        self.connect_btn = tk.Button(control_inner, text="▶ Conectar",
                                    font=('Segoe UI', 12, 'bold'),
                                    bg=self.colors['success'],
                                    fg='white',
                                    relief=tk.FLAT,
                                    cursor='hand2',
                                    width=15,
                                    command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 30))
        
        # Slider de umbral
        threshold_label = tk.Label(control_inner, text="Umbral:",
                                  font=('Segoe UI', 11, 'bold'),
                                  bg=self.colors['bg_medium'],
                                  fg=self.colors['text'])
        threshold_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.threshold_var = tk.IntVar(value=self.threshold)
        self.threshold_scale = tk.Scale(control_inner, from_=1500, to=3500,
                                        orient=tk.HORIZONTAL, length=150,
                                        variable=self.threshold_var,
                                        bg=self.colors['bg_medium'],
                                        fg=self.colors['text'],
                                        highlightthickness=0,
                                        troughcolor=self.colors['bg_light'],
                                        activebackground=self.colors['accent'],
                                        command=self.update_threshold)
        self.threshold_scale.pack(side=tk.LEFT, padx=(0, 20))
        
        # Estado de conexión
        self.status_label = tk.Label(control_inner, text="⚫ Desconectado",
                                    font=('Segoe UI', 11),
                                    bg=self.colors['bg_medium'],
                                    fg=self.colors['warning'])
        self.status_label.pack(side=tk.RIGHT)
        
        # ==== ÁREA PRINCIPAL ====
        content_frame = tk.Frame(main_frame, bg=self.colors['bg_dark'])
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # ==== INDICADORES LATERALES ====
        indicators_frame = tk.Frame(content_frame, bg=self.colors['bg_medium'],
                                   width=200)
        indicators_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        indicators_frame.pack_propagate(False)
        
        indicators_inner = tk.Frame(indicators_frame, bg=self.colors['bg_medium'])
        indicators_inner.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        
        # Indicador de BPM
        bpm_title = tk.Label(indicators_inner, text="❤ BPM",
                            font=('Segoe UI', 14, 'bold'),
                            bg=self.colors['bg_medium'],
                            fg=self.colors['text'])
        bpm_title.pack(pady=(0, 5))
        
        self.bpm_label = tk.Label(indicators_inner, text="--",
                                 font=('Consolas', 48, 'bold'),
                                 bg=self.colors['bg_medium'],
                                 fg=self.colors['accent'])
        self.bpm_label.pack(pady=(0, 20))
        
        # Indicador de latido (corazón animado)
        self.heart_label = tk.Label(indicators_inner, text="♥",
                                   font=('Segoe UI', 72),
                                   bg=self.colors['bg_medium'],
                                   fg=self.colors['accent'])
        self.heart_label.pack(pady=20)
        
        # Indicador de leads
        self.leads_label = tk.Label(indicators_inner, text="Electrodos: --",
                                   font=('Segoe UI', 12),
                                   bg=self.colors['bg_medium'],
                                   fg=self.colors['text_dim'])
        self.leads_label.pack(pady=(30, 10))
        
        # Lectura actual
        reading_title = tk.Label(indicators_inner, text="Lectura ADC",
                                font=('Segoe UI', 12, 'bold'),
                                bg=self.colors['bg_medium'],
                                fg=self.colors['text'])
        reading_title.pack(pady=(20, 5))
        
        self.reading_label = tk.Label(indicators_inner, text="----",
                                     font=('Consolas', 24, 'bold'),
                                     bg=self.colors['bg_medium'],
                                     fg=self.colors['ecg_line'])
        self.reading_label.pack()
        
        # ==== CANVAS PARA GRÁFICA ECG ====
        graph_frame = tk.Frame(content_frame, bg=self.colors['bg_medium'],
                              relief=tk.FLAT, bd=0)
        graph_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(graph_frame, bg=self.colors['bg_dark'],
                               highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Bind resize event
        self.canvas.bind('<Configure>', self.on_canvas_resize)
        
    def refresh_ports(self):
        """Actualizar lista de puertos COM disponibles"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
            
    def update_threshold(self, value):
        """Actualizar umbral de detección"""
        self.threshold = int(value)
        
    def toggle_connection(self):
        """Conectar o desconectar del puerto serial"""
        if self.is_running:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        """Conectar al puerto serial"""
        port = self.port_var.get()
        if not port:
            self.status_label.config(text="⚠ Seleccione un puerto", 
                                    fg=self.colors['warning'])
            return
            
        try:
            self.serial_port = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.5)  # Esperar a que se estabilice
            self.is_running = True
            
            # Iniciar hilo de lectura
            self.read_thread = threading.Thread(target=self.read_serial_data, 
                                               daemon=True)
            self.read_thread.start()
            
            # Actualizar UI
            self.connect_btn.config(text="⏹ Detener", bg=self.colors['accent'])
            self.status_label.config(text=f"● Conectado a {port}", 
                                    fg=self.colors['success'])
            self.port_combo.config(state='disabled')
            
        except Exception as e:
            self.status_label.config(text=f"⚠ Error: {str(e)[:30]}", 
                                    fg=self.colors['accent'])
            
    def disconnect(self):
        """Desconectar del puerto serial"""
        self.is_running = False
        
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            
        self.connect_btn.config(text="▶ Conectar", bg=self.colors['success'])
        self.status_label.config(text="⚫ Desconectado", fg=self.colors['warning'])
        self.port_combo.config(state='readonly')
        
    def read_serial_data(self):
        """Leer datos del puerto serial en un hilo separado"""
        while self.is_running:
            try:
                if self.serial_port and self.serial_port.is_open:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    
                    if line:
                        if line == "LEADS_OFF":
                            self.leads_off = True
                        else:
                            self.leads_off = False
                            try:
                                raw_value = int(line)
                                current_time = time.time()
                                
                                # Guardar dato crudo
                                self.raw_buffer.append(raw_value)
                                
                                # Aplicar filtrado digital en cascada
                                if self.filter_enabled:
                                    filtered_value = self.apply_filters(raw_value)
                                else:
                                    filtered_value = raw_value
                                
                                self.data_buffer.append(filtered_value)
                                self.time_buffer.append(current_time)
                                
                                # Detección de latido (usar datos filtrados)
                                self.detect_beat(filtered_value, current_time)
                                
                            except ValueError:
                                pass
            except Exception as e:
                if self.is_running:
                    print(f"Error leyendo serial: {e}")
                break
    
    def apply_filters(self, raw_value):
        """Aplicar filtros digitales en cascada a una sola muestra"""
        try:
            # Convertir a array numpy para el filtrado
            x = np.array([float(raw_value)])
            
            # 1. Filtro Notch 60Hz (eliminar interferencia de red eléctrica)
            y, self.notch_zi = signal.lfilter(self.notch_b, self.notch_a, x, zi=self.notch_zi)
            
            # 2. Filtro Pasa-Bajas 35Hz (eliminar ruido de alta frecuencia)
            y, self.lp_zi = signal.lfilter(self.lp_b, self.lp_a, y, zi=self.lp_zi)
            
            # 3. Filtro Pasa-Altas 0.5Hz (eliminar deriva de línea base)
            y, self.hp_zi = signal.lfilter(self.hp_b, self.hp_a, y, zi=self.hp_zi)
            
            # Restaurar nivel DC (centrar en 2048)
            filtered = y[0] + 2048
            
            # Limitar al rango del ADC
            filtered = max(0, min(4095, filtered))
            
            return int(filtered)
            
        except Exception as e:
            # Si hay error en filtrado, retornar valor crudo
            return raw_value
                
    def detect_beat(self, value, current_time):
        """Detectar latidos cardíacos (picos R)"""
        # Algoritmo simple de detección de picos
        if value > self.threshold:
            if not self.rising and value > self.last_peak_value:
                self.rising = True
        else:
            if self.rising:
                # Se detectó un pico
                time_since_last = current_time - self.last_beat_time
                
                if time_since_last > self.min_beat_interval:
                    self.beat_detected = True
                    self.beat_times.append(current_time)
                    self.last_beat_time = current_time
                    
                    # Calcular BPM
                    if len(self.beat_times) >= 2:
                        intervals = []
                        times = list(self.beat_times)
                        for i in range(1, len(times)):
                            intervals.append(times[i] - times[i-1])
                        
                        if intervals:
                            avg_interval = np.mean(intervals)
                            if avg_interval > 0:
                                self.current_bpm = int(60 / avg_interval)
                                
                    # Reproducir sonido
                    self.play_heartbeat_sound()
                    
                self.rising = False
                
        self.last_peak_value = value
        
    def play_heartbeat_sound(self):
        """Reproducir sonido de latido"""
        try:
            # Sonido de beep corto
            threading.Thread(target=lambda: winsound.Beep(800, 50), 
                           daemon=True).start()
        except:
            pass
            
    def on_canvas_resize(self, event):
        """Manejar redimensionamiento del canvas"""
        self.canvas_width = event.width
        self.canvas_height = event.height
        
    def update_plot(self):
        """Actualizar la gráfica ECG"""
        self.canvas.delete("all")
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width < 10 or height < 10:
            self.root.after(50, self.update_plot)
            return
            
        margin = 40
        graph_width = width - 2 * margin
        graph_height = height - 2 * margin
        
        # Dibujar cuadrícula
        self.draw_grid(margin, width, height, graph_width, graph_height)
        
        # Dibujar línea de umbral
        if len(self.data_buffer) > 0:
            y_min = min(self.data_buffer) if len(self.data_buffer) > 0 else 0
            y_max = max(self.data_buffer) if len(self.data_buffer) > 0 else 4095
            
            # Asegurar rango mínimo
            y_range = y_max - y_min
            if y_range < 200:
                mid = (y_max + y_min) / 2
                y_min = mid - 100
                y_max = mid + 100
                y_range = 200
                
            # Línea de umbral
            threshold_y = margin + graph_height - ((self.threshold - y_min) / y_range * graph_height)
            threshold_y = max(margin, min(height - margin, threshold_y))
            
            self.canvas.create_line(margin, threshold_y, width - margin, threshold_y,
                                   fill='#ff6b6b', width=1, dash=(5, 3))
            self.canvas.create_text(width - margin - 50, threshold_y - 10,
                                   text=f"Umbral: {self.threshold}",
                                   fill='#ff6b6b', font=('Segoe UI', 9))
        
        # Dibujar señal ECG
        if len(self.data_buffer) > 1:
            data = list(self.data_buffer)
            
            y_min = min(data)
            y_max = max(data)
            y_range = y_max - y_min
            if y_range < 200:
                mid = (y_max + y_min) / 2
                y_min = mid - 100
                y_max = mid + 100
                y_range = 200
            
            points = []
            n_points = len(data)
            
            for i, value in enumerate(data):
                x = margin + (i / n_points) * graph_width
                y = margin + graph_height - ((value - y_min) / y_range * graph_height)
                points.extend([x, y])
            
            if len(points) >= 4:
                # Dibujar línea ECG con efecto de brillo
                self.canvas.create_line(points, fill=self.colors['ecg_line'],
                                       width=2, smooth=True)
        
        # Actualizar indicadores
        self.update_indicators()
        
        # Animar corazón si se detectó latido
        if self.beat_detected:
            self.animate_heart()
            self.beat_detected = False
        
        # Programar siguiente actualización
        self.root.after(33, self.update_plot)  # ~30 FPS
        
    def draw_grid(self, margin, width, height, graph_width, graph_height):
        """Dibujar cuadrícula de fondo"""
        grid_color = self.colors['grid']
        
        # Líneas verticales
        for i in range(11):
            x = margin + (i / 10) * graph_width
            self.canvas.create_line(x, margin, x, height - margin,
                                   fill=grid_color, width=1)
        
        # Líneas horizontales
        for i in range(9):
            y = margin + (i / 8) * graph_height
            self.canvas.create_line(margin, y, width - margin, y,
                                   fill=grid_color, width=1)
        
        # Borde
        self.canvas.create_rectangle(margin, margin, width - margin, height - margin,
                                    outline=self.colors['bg_light'], width=2)
        
        # Etiquetas
        self.canvas.create_text(margin - 5, margin, text="4095",
                               fill=self.colors['text_dim'], font=('Segoe UI', 9),
                               anchor='e')
        self.canvas.create_text(margin - 5, height - margin, text="0",
                               fill=self.colors['text_dim'], font=('Segoe UI', 9),
                               anchor='e')
        self.canvas.create_text(width / 2, height - margin + 25, 
                               text="Señal ECG en tiempo real",
                               fill=self.colors['text_dim'], font=('Segoe UI', 10))
        
    def update_indicators(self):
        """Actualizar indicadores en el panel lateral"""
        # BPM
        if self.current_bpm > 0 and self.current_bpm < 250:
            self.bpm_label.config(text=str(self.current_bpm))
            
            # Color según BPM
            if 60 <= self.current_bpm <= 100:
                self.bpm_label.config(fg=self.colors['success'])
            elif self.current_bpm < 60:
                self.bpm_label.config(fg=self.colors['warning'])
            else:
                self.bpm_label.config(fg=self.colors['accent'])
        else:
            self.bpm_label.config(text="--", fg=self.colors['text_dim'])
        
        # Estado de electrodos
        if self.leads_off:
            self.leads_label.config(text="⚠ Electrodos desconectados",
                                   fg=self.colors['accent'])
        elif self.is_running:
            self.leads_label.config(text="✓ Electrodos conectados",
                                   fg=self.colors['success'])
        else:
            self.leads_label.config(text="Electrodos: --",
                                   fg=self.colors['text_dim'])
        
        # Lectura actual
        if len(self.data_buffer) > 0:
            self.reading_label.config(text=str(self.data_buffer[-1]))
        else:
            self.reading_label.config(text="----")
            
    def animate_heart(self):
        """Animar el corazón cuando hay un latido"""
        # Efecto de pulsación
        self.heart_label.config(font=('Segoe UI', 90), fg='#ff0040')
        self.root.after(100, lambda: self.heart_label.config(
            font=('Segoe UI', 72), fg=self.colors['accent']))


def main():
    """Función principal"""
    root = tk.Tk()
    
    # Configurar ícono si existe
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    app = ECGMonitor(root)
    
    # Manejar cierre
    def on_closing():
        app.disconnect()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
