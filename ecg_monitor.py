"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                     🏥 CARDIOVIEW PRO - Monitor ECG Profesional               ║
║                                                                               ║
║  Autores: Victor, Joel y Uriel                                                ║
║  Proyecto: STM32F401 + AD8232                                                  ║
║  Versión: 2.0 Professional                                                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import collections
import time
import numpy as np
import winsound
from datetime import datetime
from scipy import signal
import math


class CardioViewPro:
    """Monitor ECG Profesional con interfaz médica avanzada"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Lectura ECG STM32")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)
        self.root.configure(bg='#0a0e17')
        
        # Estado
        self.serial_port = None
        self.is_running = False
        self.is_recording = False
        self.recording_start_time = None
        self.demo_mode = False
        self.demo_phase = 0.0  # fase interna del generador ECG
        
        # Buffers de datos
        self.data_buffer = collections.deque(maxlen=600)
        self.raw_buffer = collections.deque(maxlen=600)
        self.time_buffer = collections.deque(maxlen=600)
        self.bpm_history = collections.deque(maxlen=60)
        self.beat_times = collections.deque(maxlen=30)
        
        # Estado cardíaco
        self.current_bpm = 0
        self.last_beat_time = 0
        self.leads_off = False
        self.beat_detected = False
        self.session_beats = 0
        self.min_bpm = 999
        self.max_bpm = 0
        self.avg_bpm = 0
        
        # Detección de latidos
        self.threshold = 2800
        self.min_beat_interval = 0.3
        self.last_peak_value = 0
        self.rising = False
        
        # Filtros digitales
        self.fs = 250
        self.setup_filters()
        self.filter_enabled = True
        
        # Animación
        self.animation_phase = 0
        self.pulse_scale = 1.0
        
        # Colores del tema médico profesional
        self.colors = {
            'bg_primary': '#0a0e17',
            'bg_secondary': '#111827',
            'bg_card': '#1f2937',
            'bg_card_hover': '#283548',
            'accent_primary': '#10b981',
            'accent_danger': '#ef4444',
            'accent_warning': '#f59e0b',
            'accent_info': '#3b82f6',
            'accent_purple': '#8b5cf6',
            'text_primary': '#f9fafb',
            'text_secondary': '#9ca3af',
            'text_muted': '#6b7280',
            'ecg_line': '#22d3ee',
            'ecg_glow': '#06b6d4',
            'grid_primary': '#1f2937',
            'grid_secondary': '#374151',
            'border': '#374151',
            'success': '#10b981',
            'heart_red': '#f43f5e',
            'heart_glow': '#fb7185'
        }
        
        self.setup_styles()
        self.create_ui()
        self.start_animation_loop()
        self.update_plot()
        self.update_clock()
        # Arrancar demo automáticamente para mostrar señal desde el inicio
        self.root.after(500, self.start_demo)
        
    def setup_filters(self):
        """Configurar filtros digitales"""
        # Pasa-bajas 35Hz
        self.lp_b, self.lp_a = signal.butter(4, 35 / (self.fs / 2), btype='low')
        self.lp_zi = signal.lfilter_zi(self.lp_b, self.lp_a) * 2048
        
        # Pasa-altas 0.5Hz
        self.hp_b, self.hp_a = signal.butter(4, 0.5 / (self.fs / 2), btype='high')
        self.hp_zi = signal.lfilter_zi(self.hp_b, self.hp_a) * 0
        
        # Notch 60Hz
        self.notch_b, self.notch_a = signal.iirnotch(60 / (self.fs / 2), 30)
        self.notch_zi = signal.lfilter_zi(self.notch_b, self.notch_a) * 2048

    def setup_styles(self):
        """Configurar estilos ttk"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Estilo para combobox
        style.configure('Pro.TCombobox',
                       fieldbackground=self.colors['bg_card'],
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       arrowcolor=self.colors['accent_primary'])
        
    def create_ui(self):
        """Crear interfaz de usuario completa"""
        
        # === HEADER ===
        self.create_header()

        # === BANNER DE TÍTULO ===
        self.create_title_banner()
        
        # === CUERPO PRINCIPAL ===
        main_container = tk.Frame(self.root, bg=self.colors['bg_primary'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Panel izquierdo - Stats
        self.create_left_panel(main_container)
        
        # Panel central - ECG
        self.create_center_panel(main_container)
        
        # Panel derecho - Vitals
        self.create_right_panel(main_container)

    def create_title_banner(self):
        """Banner de título del proyecto"""
        banner = tk.Frame(self.root, bg='#0d1520', height=56)
        banner.pack(fill=tk.X, padx=20, pady=(0, 10))
        banner.pack_propagate(False)

        # Franja de acento izquierda
        accent = tk.Frame(banner, bg=self.colors['accent_primary'], width=5)
        accent.pack(side=tk.LEFT, fill=tk.Y)

        # Contenido del banner
        content = tk.Frame(banner, bg='#0d1520')
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=18)

        # Fila superior: nombre del proyecto
        title_lbl = tk.Label(
            content,
            text="📡  LECTURA ECG CON STM32F401 + AD8232",
            font=('Segoe UI', 14, 'bold'),
            bg='#0d1520',
            fg=self.colors['text_primary']
        )
        title_lbl.pack(anchor='w', pady=(6, 0))

        # Fila inferior: autores / descripción
        sub_lbl = tk.Label(
            content,
            text="Autores: Victor · Joel · Uriel  |  Adquisición de señal cardíaca en tiempo real",
            font=('Segoe UI', 9),
            bg='#0d1520',
            fg=self.colors['text_muted']
        )
        sub_lbl.pack(anchor='w', pady=(1, 0))

        # Etiqueta de versión a la derecha
        ver_frame = tk.Frame(banner, bg='#0d1520')
        ver_frame.pack(side=tk.RIGHT, padx=18, fill=tk.Y)

        ver_lbl = tk.Label(
            ver_frame,
            text="v2.0",
            font=('Consolas', 11, 'bold'),
            bg=self.colors['accent_primary'],
            fg='white',
            padx=10, pady=3
        )
        ver_lbl.pack(anchor='e', pady=14)
        
    def create_header(self):
        """Crear barra superior profesional"""
        header = tk.Frame(self.root, bg=self.colors['bg_secondary'], height=70)
        header.pack(fill=tk.X, padx=20, pady=20)
        header.pack_propagate(False)
        
        # Logo y título
        logo_frame = tk.Frame(header, bg=self.colors['bg_secondary'])
        logo_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        # Icono de corazón con efecto
        self.logo_heart = tk.Label(logo_frame, text="♥", 
                                   font=('Segoe UI', 28),
                                   bg=self.colors['bg_secondary'],
                                   fg=self.colors['heart_red'])
        self.logo_heart.pack(side=tk.LEFT, padx=(0, 10))
        
        title_container = tk.Frame(logo_frame, bg=self.colors['bg_secondary'])
        title_container.pack(side=tk.LEFT)
        
        tk.Label(title_container, text="Lectura ECG STM32",
                font=('Segoe UI', 20, 'bold'),
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_primary']).pack(anchor='w')
        
        tk.Label(title_container, text="Monitor ECG · STM32F401 + AD8232",
                font=('Segoe UI', 10),
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_muted']).pack(anchor='w')
        
        # Panel de control central
        control_frame = tk.Frame(header, bg=self.colors['bg_secondary'])
        control_frame.pack(side=tk.LEFT, expand=True)
        
        controls_inner = tk.Frame(control_frame, bg=self.colors['bg_secondary'])
        controls_inner.pack()
        
        # Puerto COM
        port_container = tk.Frame(controls_inner, bg=self.colors['bg_secondary'])
        port_container.pack(side=tk.LEFT, padx=10)
        
        tk.Label(port_container, text="PUERTO", 
                font=('Segoe UI', 8, 'bold'),
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_muted']).pack()
        
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(port_container, textvariable=self.port_var,
                                       width=12, state='readonly', style='Pro.TCombobox')
        self.port_combo.pack(pady=2)
        self.refresh_ports()
        
        # Botón refrescar
        self.refresh_btn = tk.Button(controls_inner, text="⟳",
                                    font=('Segoe UI', 14),
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['text_secondary'],
                                    relief=tk.FLAT, bd=0,
                                    cursor='hand2', width=3,
                                    command=self.refresh_ports)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Botón conectar
        self.connect_btn = tk.Button(controls_inner, text="▶ INICIAR",
                                    font=('Segoe UI', 11, 'bold'),
                                    bg=self.colors['accent_primary'],
                                    fg='white', relief=tk.FLAT, bd=0,
                                    cursor='hand2', width=12, height=2,
                                    command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=10)

        # Botón DEMO
        self.demo_btn = tk.Button(controls_inner, text="⚡ DEMO",
                                  font=('Segoe UI', 11, 'bold'),
                                  bg=self.colors['accent_purple'],
                                  fg='white', relief=tk.FLAT, bd=0,
                                  cursor='hand2', width=10, height=2,
                                  command=self.toggle_demo)
        self.demo_btn.pack(side=tk.LEFT, padx=5)
        
        # Slider umbral
        threshold_container = tk.Frame(controls_inner, bg=self.colors['bg_secondary'])
        threshold_container.pack(side=tk.LEFT, padx=20)
        
        tk.Label(threshold_container, text="SENSIBILIDAD",
                font=('Segoe UI', 8, 'bold'),
                bg=self.colors['bg_secondary'],
                fg=self.colors['text_muted']).pack()
        
        self.threshold_var = tk.IntVar(value=self.threshold)
        self.threshold_scale = tk.Scale(threshold_container, from_=1500, to=3500,
                                        orient=tk.HORIZONTAL, length=120,
                                        variable=self.threshold_var,
                                        bg=self.colors['bg_secondary'],
                                        fg=self.colors['text_primary'],
                                        highlightthickness=0, bd=0,
                                        troughcolor=self.colors['bg_card'],
                                        activebackground=self.colors['accent_primary'],
                                        command=self.update_threshold,
                                        showvalue=False)
        self.threshold_scale.pack()
        
        # Reloj y estado
        right_info = tk.Frame(header, bg=self.colors['bg_secondary'])
        right_info.pack(side=tk.RIGHT, padx=20)
        
        self.clock_label = tk.Label(right_info, text="00:00:00",
                                   font=('Consolas', 18, 'bold'),
                                   bg=self.colors['bg_secondary'],
                                   fg=self.colors['text_primary'])
        self.clock_label.pack()
        
        self.status_indicator = tk.Label(right_info, text="● DESCONECTADO",
                                        font=('Segoe UI', 9, 'bold'),
                                        bg=self.colors['bg_secondary'],
                                        fg=self.colors['accent_warning'])
        self.status_indicator.pack()
        
    def create_left_panel(self, parent):
        """Panel izquierdo con estadísticas"""
        left_panel = tk.Frame(parent, bg=self.colors['bg_primary'], width=220)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        left_panel.pack_propagate(False)
        
        # Tarjeta de sesión
        session_card = self.create_card(left_panel, "📊 SESIÓN")
        session_card.pack(fill=tk.X, pady=(0, 15))
        
        self.session_time_label = tk.Label(session_card, text="00:00:00",
                                           font=('Consolas', 24, 'bold'),
                                           bg=self.colors['bg_card'],
                                           fg=self.colors['accent_info'])
        self.session_time_label.pack(pady=(5, 10))
        
        self.beats_label = tk.Label(session_card, text="0 latidos",
                                   font=('Segoe UI', 11),
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['text_secondary'])
        self.beats_label.pack()
        
        # Tarjeta de estadísticas
        stats_card = self.create_card(left_panel, "📈 ESTADÍSTICAS")
        stats_card.pack(fill=tk.X, pady=(0, 15))
        
        # Min BPM
        self.create_stat_row(stats_card, "Mínimo", "---", 'min_bpm_value', self.colors['accent_info'])
        # Max BPM
        self.create_stat_row(stats_card, "Máximo", "---", 'max_bpm_value', self.colors['accent_danger'])
        # Promedio
        self.create_stat_row(stats_card, "Promedio", "---", 'avg_bpm_value', self.colors['accent_primary'])
        
        # Tarjeta de filtros
        filter_card = self.create_card(left_panel, "⚡ FILTROS DSP")
        filter_card.pack(fill=tk.X)
        
        self.filter_status = tk.Label(filter_card, text="✓ Activos",
                                     font=('Segoe UI', 12, 'bold'),
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['accent_primary'])
        self.filter_status.pack(pady=5)
        
        filters_info = tk.Label(filter_card, 
                               text="• Notch 60Hz\n• Pasa-bajas 35Hz\n• Pasa-altas 0.5Hz",
                               font=('Segoe UI', 9),
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_muted'],
                               justify=tk.LEFT)
        filters_info.pack(pady=5)
        
    def create_center_panel(self, parent):
        """Panel central con gráfica ECG"""
        center_panel = tk.Frame(parent, bg=self.colors['bg_card'])
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))
        
        # Header del panel
        header = tk.Frame(center_panel, bg=self.colors['bg_card'])
        header.pack(fill=tk.X, padx=15, pady=10)
        
        tk.Label(header, text="📟 ELECTROCARDIOGRAMA",
                font=('Segoe UI', 12, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(side=tk.LEFT)
        
        self.lead_label = tk.Label(header, text="Lead II",
                                  font=('Segoe UI', 10),
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['text_muted'])
        self.lead_label.pack(side=tk.RIGHT)
        
        # Canvas para ECG
        self.canvas = tk.Canvas(center_panel, bg='#050810', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        self.canvas.bind('<Configure>', self.on_canvas_resize)
        
    def create_right_panel(self, parent):
        """Panel derecho con signos vitales"""
        right_panel = tk.Frame(parent, bg=self.colors['bg_primary'], width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        right_panel.pack_propagate(False)
        
        # Tarjeta BPM principal
        bpm_card = tk.Frame(right_panel, bg=self.colors['bg_card'])
        bpm_card.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(bpm_card, text="❤ FRECUENCIA CARDÍACA",
                font=('Segoe UI', 10, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_muted']).pack(pady=(15, 5))
        
        self.bpm_label = tk.Label(bpm_card, text="---",
                                 font=('Consolas', 64, 'bold'),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['accent_primary'])
        self.bpm_label.pack()
        
        tk.Label(bpm_card, text="BPM",
                font=('Segoe UI', 14),
                bg=self.colors['bg_card'],
                fg=self.colors['text_secondary']).pack(pady=(0, 5))
        
        self.bpm_status = tk.Label(bpm_card, text="Sin datos",
                                  font=('Segoe UI', 10),
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['text_muted'])
        self.bpm_status.pack(pady=(0, 15))
        
        # Corazón animado
        heart_card = tk.Frame(right_panel, bg=self.colors['bg_card'])
        heart_card.pack(fill=tk.X, pady=(0, 15))
        
        self.heart_canvas = tk.Canvas(heart_card, width=220, height=150,
                                      bg=self.colors['bg_card'], highlightthickness=0)
        self.heart_canvas.pack(pady=15)
        
        # Electrodo status
        electrode_card = self.create_card(right_panel, "🔌 ELECTRODOS")
        electrode_card.pack(fill=tk.X, pady=(0, 15))
        
        self.electrode_status = tk.Label(electrode_card, text="Sin conexión",
                                        font=('Segoe UI', 11),
                                        bg=self.colors['bg_card'],
                                        fg=self.colors['text_muted'])
        self.electrode_status.pack(pady=10)
        
        # Valor ADC
        adc_card = self.create_card(right_panel, "📶 SEÑAL ADC")
        adc_card.pack(fill=tk.X)
        
        self.adc_label = tk.Label(adc_card, text="----",
                                 font=('Consolas', 28, 'bold'),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['ecg_line'])
        self.adc_label.pack(pady=(5, 10))
        
        self.signal_quality = tk.Label(adc_card, text="Calidad: ---",
                                      font=('Segoe UI', 10),
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['text_muted'])
        self.signal_quality.pack(pady=(0, 10))
        
    def create_card(self, parent, title):
        """Crear tarjeta con estilo"""
        card = tk.Frame(parent, bg=self.colors['bg_card'])
        
        header = tk.Label(card, text=title,
                         font=('Segoe UI', 10, 'bold'),
                         bg=self.colors['bg_card'],
                         fg=self.colors['text_muted'])
        header.pack(pady=(15, 5), padx=15, anchor='w')
        
        return card
    
    def create_stat_row(self, parent, label, value, attr_name, color):
        """Crear fila de estadística"""
        row = tk.Frame(parent, bg=self.colors['bg_card'])
        row.pack(fill=tk.X, padx=15, pady=5)
        
        tk.Label(row, text=label,
                font=('Segoe UI', 10),
                bg=self.colors['bg_card'],
                fg=self.colors['text_secondary']).pack(side=tk.LEFT)
        
        value_label = tk.Label(row, text=value,
                              font=('Consolas', 12, 'bold'),
                              bg=self.colors['bg_card'],
                              fg=color)
        value_label.pack(side=tk.RIGHT)
        setattr(self, attr_name, value_label)
        
    # ========== FUNCIONES DE CONEXIÓN ==========
    
    def refresh_ports(self):
        """Actualizar puertos COM"""
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
            
    def update_threshold(self, value):
        """Actualizar umbral"""
        self.threshold = int(value)
        
    def toggle_connection(self):
        """Conectar/desconectar"""
        if self.is_running:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        """Conectar al puerto serial"""
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("Aviso", "Seleccione un puerto COM")
            return
            
        try:
            self.serial_port = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.5)
            self.is_running = True
            self.recording_start_time = time.time()
            self.session_beats = 0
            self.min_bpm = 999
            self.max_bpm = 0
            
            self.read_thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.read_thread.start()
            
            self.connect_btn.config(text="⏹ DETENER", bg=self.colors['accent_danger'])
            self.status_indicator.config(text="● EN LÍNEA", fg=self.colors['accent_primary'])
            self.port_combo.config(state='disabled')
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo conectar: {e}")
            
    def disconnect(self):
        """Desconectar"""
        self.is_running = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            
        self.connect_btn.config(text="▶ INICIAR", bg=self.colors['accent_primary'])
        self.status_indicator.config(text="● DESCONECTADO", fg=self.colors['accent_warning'])
        self.port_combo.config(state='readonly')
        
    def read_serial_data(self):
        """Leer datos seriales"""
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
                                self.raw_buffer.append(raw_value)
                                
                                if self.filter_enabled:
                                    filtered = self.apply_filters(raw_value)
                                else:
                                    filtered = raw_value
                                    
                                self.data_buffer.append(filtered)
                                self.time_buffer.append(current_time)
                                self.detect_beat(filtered, current_time)
                            except ValueError:
                                pass
            except:
                break

    # ========== MODO DEMO / SIMULACIÓN ==========

    def toggle_demo(self):
        """Activar o desactivar el modo demo"""
        if self.is_running and not self.demo_mode:
            # Hay una conexión serial real activa — no tocar
            return
        if self.demo_mode:
            self.stop_demo()
        else:
            self.start_demo()

    def start_demo(self):
        """Iniciar simulación de señal ECG"""
        self.demo_mode = True
        self.is_running = True
        self.recording_start_time = time.time()
        self.session_beats = 0
        self.min_bpm = 999
        self.max_bpm = 0
        self.demo_phase = 0.0

        self.demo_btn.config(text="⏹ DEMO", bg=self.colors['accent_danger'])
        self.connect_btn.config(state='disabled')
        self.status_indicator.config(text="● SIMULACIÓN", fg=self.colors['accent_purple'])
        self.electrode_status.config(text="✓ Simulado", fg=self.colors['accent_purple'])

        self.demo_thread = threading.Thread(target=self.run_demo_signal, daemon=True)
        self.demo_thread.start()

    def stop_demo(self):
        """Detener simulación"""
        self.demo_mode = False
        self.is_running = False

        self.demo_btn.config(text="⚡ DEMO", bg=self.colors['accent_purple'])
        self.connect_btn.config(state='normal')
        self.status_indicator.config(text="● DESCONECTADO", fg=self.colors['accent_warning'])
        self.electrode_status.config(text="Sin conexión", fg=self.colors['text_muted'])

    def generate_ecg_sample(self, phase):
        """
        Genera un valor ADC sintético que imita la forma de onda PQRST.
        phase va de 0.0 a 1.0 representando un ciclo cardiaco completo.
        Retorna un valor entre 0 y 4095 (12-bit ADC centrado en ~2048).
        """
        # Línea base
        value = 0.0

        # --- Onda P (despolarización auricular) ---
        p_center, p_width, p_amp = 0.10, 0.04, 0.08
        value += p_amp * math.exp(-((phase - p_center) ** 2) / (2 * p_width ** 2))

        # --- Segmento PR (plano) — ya cubierto por ausencia de señal ---

        # --- Onda Q ---
        q_center, q_width, q_amp = 0.27, 0.008, -0.05
        value += q_amp * math.exp(-((phase - q_center) ** 2) / (2 * q_width ** 2))

        # --- Onda R (pico principal) ---
        r_center, r_width, r_amp = 0.30, 0.012, 1.0
        value += r_amp * math.exp(-((phase - r_center) ** 2) / (2 * r_width ** 2))

        # --- Onda S ---
        s_center, s_width, s_amp = 0.33, 0.010, -0.18
        value += s_amp * math.exp(-((phase - s_center) ** 2) / (2 * s_width ** 2))

        # --- Onda T (repolarización ventricular) ---
        t_center, t_width, t_amp = 0.55, 0.06, 0.22
        value += t_amp * math.exp(-((phase - t_center) ** 2) / (2 * t_width ** 2))

        # Escalar a rango ADC (centrado en 2048, amplitud ±800)
        noise = np.random.normal(0, 0.008)  # ruido fisiológico suave
        raw_adc = int(2048 + (value + noise) * 800)
        return max(0, min(4095, raw_adc))

    def run_demo_signal(self):
        """Hilo que genera muestras ECG sintéticas a ~250 Hz"""
        sample_interval = 1.0 / self.fs  # 4 ms por muestra
        # BPM base ~75 → periodo cardiaco ~0.8 s
        bpm_base = 75
        # Variar BPM suavemente entre 70-80 a lo largo del tiempo
        bpm_vary_speed = 0.03  # rad/s de variación
        vary_phase = 0.0

        while self.demo_mode and self.is_running:
            t0 = time.time()

            # BPM ligeramente variable (variabilidad de frecuencia cardíaca)
            vary_phase += bpm_vary_speed * sample_interval
            bpm = bpm_base + 5 * math.sin(vary_phase)
            period = 60.0 / bpm  # segundos por ciclo

            # Avanzar fase dentro del ciclo cardiaco
            self.demo_phase += sample_interval / period
            if self.demo_phase >= 1.0:
                self.demo_phase -= 1.0

            raw_value = self.generate_ecg_sample(self.demo_phase)
            current_time = time.time()

            self.raw_buffer.append(raw_value)
            self.data_buffer.append(raw_value)
            self.time_buffer.append(current_time)
            self.detect_beat(raw_value, current_time)

            # Mantener tasa de muestreo
            elapsed = time.time() - t0
            sleep_time = sample_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    def apply_filters(self, raw_value):
        """Aplicar filtros digitales"""
        try:
            x = np.array([float(raw_value)])
            y, self.notch_zi = signal.lfilter(self.notch_b, self.notch_a, x, zi=self.notch_zi)
            y, self.lp_zi = signal.lfilter(self.lp_b, self.lp_a, y, zi=self.lp_zi)
            y, self.hp_zi = signal.lfilter(self.hp_b, self.hp_a, y, zi=self.hp_zi)
            return int(max(0, min(4095, y[0] + 2048)))
        except:
            return raw_value
            
    def detect_beat(self, value, current_time):
        """Detectar latidos"""
        if value > self.threshold:
            if not self.rising and value > self.last_peak_value:
                self.rising = True
        else:
            if self.rising:
                time_since = current_time - self.last_beat_time
                if time_since > self.min_beat_interval:
                    self.beat_detected = True
                    self.beat_times.append(current_time)
                    self.last_beat_time = current_time
                    self.session_beats += 1
                    
                    if len(self.beat_times) >= 2:
                        intervals = []
                        times = list(self.beat_times)
                        for i in range(1, len(times)):
                            intervals.append(times[i] - times[i-1])
                        if intervals:
                            avg = np.mean(intervals)
                            if avg > 0:
                                self.current_bpm = int(60 / avg)
                                self.bpm_history.append(self.current_bpm)
                                if self.current_bpm < self.min_bpm:
                                    self.min_bpm = self.current_bpm
                                if self.current_bpm > self.max_bpm:
                                    self.max_bpm = self.current_bpm
                                    
                    self.play_heartbeat()
                self.rising = False
        self.last_peak_value = value
        
    def play_heartbeat(self):
        """Reproducir sonido"""
        try:
            threading.Thread(target=lambda: winsound.Beep(600, 40), daemon=True).start()
        except:
            pass
            
    # ========== ACTUALIZACIÓN DE UI ==========
    
    def update_clock(self):
        """Actualizar reloj"""
        now = datetime.now().strftime("%H:%M:%S")
        self.clock_label.config(text=now)
        
        if self.is_running and self.recording_start_time:
            elapsed = int(time.time() - self.recording_start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self.session_time_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.beats_label.config(text=f"{self.session_beats} latidos")
            
        self.root.after(1000, self.update_clock)
        
    def start_animation_loop(self):
        """Loop de animación"""
        self.animation_phase += 0.1
        if self.animation_phase > 2 * math.pi:
            self.animation_phase = 0
            
        # Animar corazón
        self.draw_heart()
        
        # Pulso del logo
        if self.beat_detected:
            self.pulse_scale = 1.3
            self.beat_detected = False
        else:
            self.pulse_scale = max(1.0, self.pulse_scale - 0.05)
            
        self.root.after(50, self.start_animation_loop)
        
    def draw_heart(self):
        """Dibujar corazón animado"""
        self.heart_canvas.delete("all")
        cx, cy = 110, 75
        scale = 35 * self.pulse_scale
        
        # Brillo cuando late
        if self.pulse_scale > 1.05:
            glow_color = self.colors['heart_glow']
            self.heart_canvas.create_oval(cx-50, cy-40, cx+50, cy+50,
                                         fill='', outline=glow_color, width=3)
        
        # Dibujar corazón
        points = []
        for i in range(100):
            t = i * 2 * math.pi / 100
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
            points.extend([cx + x * scale / 16, cy + y * scale / 16])
            
        if len(points) >= 6:
            color = self.colors['heart_red'] if self.pulse_scale > 1.05 else '#dc2626'
            self.heart_canvas.create_polygon(points, fill=color, outline='', smooth=True)
            
    def update_plot(self):
        """Actualizar gráfica ECG"""
        self.canvas.delete("all")
        
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        if w < 50 or h < 50:
            self.root.after(50, self.update_plot)
            return
            
        margin = 50
        gw, gh = w - 2 * margin, h - 2 * margin
        
        # Dibujar cuadrícula
        self.draw_ecg_grid(margin, w, h, gw, gh)
        
        # Dibujar umbral
        if len(self.data_buffer) > 0:
            data = list(self.data_buffer)
            y_min, y_max = min(data), max(data)
            y_range = max(200, y_max - y_min)
            mid = (y_max + y_min) / 2
            y_min, y_max = mid - y_range/2, mid + y_range/2
            
            th_y = margin + gh - ((self.threshold - y_min) / y_range * gh)
            th_y = max(margin, min(h - margin, th_y))
            self.canvas.create_line(margin, th_y, w - margin, th_y,
                                   fill='#f87171', width=1, dash=(5, 3))
        
        # Dibujar señal ECG
        if len(self.data_buffer) > 1:
            data = list(self.data_buffer)
            y_min, y_max = min(data), max(data)
            y_range = max(200, y_max - y_min)
            mid = (y_max + y_min) / 2
            y_min, y_max = mid - y_range/2, mid + y_range/2
            
            points = []
            n = len(data)
            for i, v in enumerate(data):
                x = margin + (i / n) * gw
                y = margin + gh - ((v - y_min) / y_range * gh)
                points.extend([x, y])
                
            if len(points) >= 4:
                # Efecto glow
                self.canvas.create_line(points, fill=self.colors['ecg_glow'],
                                       width=4, smooth=True)
                self.canvas.create_line(points, fill=self.colors['ecg_line'],
                                       width=2, smooth=True)
        
        # Actualizar indicadores
        self.update_vitals()
        
        self.root.after(33, self.update_plot)
        
    def draw_ecg_grid(self, margin, w, h, gw, gh):
        """Dibujar cuadrícula médica"""
        # Cuadrícula fina
        for i in range(51):
            x = margin + (i / 50) * gw
            self.canvas.create_line(x, margin, x, h - margin,
                                   fill=self.colors['grid_primary'], width=1)
        for i in range(31):
            y = margin + (i / 30) * gh
            self.canvas.create_line(margin, y, w - margin, y,
                                   fill=self.colors['grid_primary'], width=1)
            
        # Cuadrícula gruesa
        for i in range(11):
            x = margin + (i / 10) * gw
            self.canvas.create_line(x, margin, x, h - margin,
                                   fill=self.colors['grid_secondary'], width=1)
        for i in range(7):
            y = margin + (i / 6) * gh
            self.canvas.create_line(margin, y, w - margin, y,
                                   fill=self.colors['grid_secondary'], width=1)
            
        # Borde
        self.canvas.create_rectangle(margin, margin, w - margin, h - margin,
                                    outline=self.colors['border'], width=2)
                                    
    def update_vitals(self):
        """Actualizar indicadores vitales"""
        # BPM
        if 30 < self.current_bpm < 200:
            self.bpm_label.config(text=str(self.current_bpm))
            if 60 <= self.current_bpm <= 100:
                self.bpm_label.config(fg=self.colors['accent_primary'])
                self.bpm_status.config(text="Ritmo normal", fg=self.colors['accent_primary'])
            elif self.current_bpm < 60:
                self.bpm_label.config(fg=self.colors['accent_info'])
                self.bpm_status.config(text="Bradicardia", fg=self.colors['accent_info'])
            else:
                self.bpm_label.config(fg=self.colors['accent_danger'])
                self.bpm_status.config(text="Taquicardia", fg=self.colors['accent_danger'])
        else:
            self.bpm_label.config(text="---", fg=self.colors['text_muted'])
            self.bpm_status.config(text="Sin datos", fg=self.colors['text_muted'])
            
        # Estadísticas
        if self.min_bpm < 999:
            self.min_bpm_value.config(text=f"{self.min_bpm} BPM")
        if self.max_bpm > 0:
            self.max_bpm_value.config(text=f"{self.max_bpm} BPM")
        if len(self.bpm_history) > 0:
            avg = int(np.mean(list(self.bpm_history)))
            self.avg_bpm_value.config(text=f"{avg} BPM")
            
        # Electrodos
        if self.leads_off:
            self.electrode_status.config(text="⚠ Desconectados", fg=self.colors['accent_danger'])
        elif self.is_running:
            self.electrode_status.config(text="✓ Conectados", fg=self.colors['accent_primary'])
        else:
            self.electrode_status.config(text="Sin conexión", fg=self.colors['text_muted'])
            
        # ADC
        if len(self.data_buffer) > 0:
            val = self.data_buffer[-1]
            self.adc_label.config(text=str(val))
            
            # Calidad de señal
            if len(self.data_buffer) > 10:
                std = np.std(list(self.data_buffer)[-50:])
                if std > 100:
                    self.signal_quality.config(text="Calidad: Buena", fg=self.colors['accent_primary'])
                elif std > 30:
                    self.signal_quality.config(text="Calidad: Regular", fg=self.colors['accent_warning'])
                else:
                    self.signal_quality.config(text="Calidad: Débil", fg=self.colors['accent_danger'])
                    
    def on_canvas_resize(self, event):
        """Manejar resize"""
        pass


def main():
    root = tk.Tk()
    
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    app = CardioViewPro(root)
    
    def on_closing():
        app.disconnect()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
