import sys
import subprocess
import os
from subprocess import CREATE_NO_WINDOW

# Auto-instalador de dependencias: se encarga de instalar requirements.txt si falta algo.
try:
    import customtkinter as ctk
    from PIL import Image
except ImportError:
    print("Instalando dependencias iniciales por primera vez (Solo tomará unos segundos)...")
    try:
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        if os.path.exists(req_path):
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", req_path])
        else:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "customtkinter", "Pillow", "PyYAML"])
        print("¡Listo! Reiniciando programa...")
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        print(f"Error instalando dependencias: {e}")
        input("Presiona Enter para salir...")
        sys.exit(1)

import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext, ttk
import threading
import json
from pathlib import Path
import queue
import re
import zipfile
try:
    import yaml
except ImportError:
    yaml = None
import socket
import shutil
import urllib.request
import urllib.error

# Import our new styles configuration and Network Manager
import styles
from network_manager import TunnelController

class MinecraftLauncher:
    def __init__(self, root):
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.title("Minecraft Server Launcher")
        self.root.geometry("1100x750")

        self.styles = styles.apply_styles()
        self.root.configure(fg_color=self.styles["colors"]["bg"])

        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            
            icon_path = os.path.join(base_path, "icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception:
            pass

        if os.name == 'nt':
            appdata = os.getenv('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
            self.data_dir = Path(appdata) / "MinecraftServerLauncher"
        else:
            self.data_dir = Path.home() / ".minecraft_launcher"
            
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.servers_file = self.data_dir / "servers.json"
        
        self.servers = self.load_servers()

        self.server_processes = {}  
        self.server_consoles = {}   
        self.console_tabs_index = {}
        self.active_players = {}    

        self.selected_server = None
        
        # Public Network Integration (Dual Tunnel)
        self.tunnel_controller = TunnelController(self.data_dir)

        # Optimization: Log queue and periodic UI update
        self.log_queue = queue.Queue()
        self.log_patterns = {
            "error": re.compile(r'ERROR|Exception|Failed|Error', re.IGNORECASE),
            "warn": re.compile(r'WARN|WARNING', re.IGNORECASE),
            "info": re.compile(r'INFO', re.IGNORECASE),
            "fatal": re.compile(r'FATAL|CRITICAL', re.IGNORECASE)
        }
        self.player_join_pattern = re.compile(r'([a-zA-Z0-9_]{3,16})\s+joined the game')
        self.player_leave_pattern = re.compile(r'([a-zA-Z0-9_]{3,16})\s+left the game')
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

        self.suggestion_commands = ["/op ", "/gamemode ", "/tp ", "/deop ", "/pl", "/stop", "/say ", "/whitelist "]
        self.suggestion_frame = None

        self.setup_ui()
        
        # Link callbacks
        self.tunnel_controller.set_callbacks(self._on_tunnel_log, self._on_tunnel_status)
        
        # Start the UI update loop
        self.update_ui_logs()

    def on_closing(self):
        if self.tunnel_controller.is_running:
            self.tunnel_controller.stop()
            
        if self.server_processes:
            self.root.withdraw() # Hide window while we shut down cleanly
            for path_key, process in list(self.server_processes.items()):
                try:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                except: pass
            
            # Wait up to 5 seconds for graceful shutdown
            for process in self.server_processes.values():
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    
        self.root.destroy()

    def get_server_port(self, path_key):
        props_path = Path(path_key) / "server.properties"
        if props_path.exists():
            try:
                for line in props_path.read_text().splitlines():
                    if line.startswith("server-port="):
                        return int(line.split("=")[1].strip())
            except: pass
        return 25565

    def is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('localhost', port)) == 0

    def load_servers(self):
        local_legacy_file = Path("servers.json")
        data = {}
        if local_legacy_file.exists():
            try:
                with open(local_legacy_file, 'r') as f:
                    content = f.read().strip()
                    # Handle multiple JSON objects or extra data by taking only the first one
                    try:
                        legacy_data = json.loads(content)
                    except json.JSONDecodeError:
                        # Extract only the first valid JSON block if corrupted
                        legacy_data = {}
                        # Simple stack-based balancer to find the first complete { ... } object
                        try:
                            start_idx = content.find('{')
                            if start_idx != -1:
                                count = 0
                                for i in range(start_idx, len(content)):
                                    if content[i] == '{': count += 1
                                    elif content[i] == '}':
                                        count -= 1
                                        if count == 0:
                                            legacy_data = json.loads(content[start_idx:i+1])
                                            break
                        except:
                            legacy_data = {}
                    
                    for name, path in legacy_data.items():
                        if isinstance(path, str):
                            data[path] = {"name": name, "version": "Vanilla", "java_path": "java", "type": "Vanilla"}
                        else:
                            data = legacy_data
                            for k, v in data.items():
                                if "type" not in v:
                                    v["type"] = "Vanilla"
                            break
                local_legacy_file.unlink()
                self._save_to_path(self.servers_file, data)
                return data
            except Exception as e:
                print(f"Error migrating local servers: {e}")

        if self.servers_file.exists():
            try:
                with open(self.servers_file, 'r') as f:
                    data = json.load(f)
                    for key, val in data.items():
                        if "type" not in val:
                            val["type"] = "Vanilla"
                    return data
            except Exception as e:
                # If persistent file is also corrupted, try similar cleanup
                try:
                    with open(self.servers_file, 'r') as f:
                        content = f.read().strip()
                        # Extract first block (brute force balance)
                        count = 0
                        for i, c in enumerate(content):
                            if c == '{': count += 1
                            elif c == '}':
                                count -= 1
                                if count == 0:
                                    return json.loads(content[:i+1])
                except:
                    print(f"Error loading persistent servers: {e}")
        return {}

    def save_servers(self):
        self._save_to_path(self.servers_file, self.servers)

    def _save_to_path(self, filepath, data):
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save to {filepath}: {e}")

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        left_frame = ctk.CTkFrame(main_frame, fg_color=self.styles["colors"]["fg"], corner_radius=10, width=280)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0,10))
        left_frame.pack_propagate(False)

        # Header Title Area
        header_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        list_title = ctk.CTkLabel(header_frame, text="Servers", font=self.styles["fonts"]["heading"], text_color=self.styles["colors"]["text"])
        list_title.pack(side=tk.LEFT)
        
        # Network config gear
        ctk.CTkButton(header_frame, text="⚙ Red IP", width=100, 
                     font=self.styles["fonts"]["body"], 
                     fg_color="transparent", 
                     text_color=self.styles["colors"]["primary"],
                     hover_color=self.styles["colors"]["bg"],
                     command=self.open_network_config).pack(side=tk.RIGHT)

        btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=5, padx=10)
        
        ctk.CTkButton(btn_frame, text="Create Server", font=self.styles["fonts"]["body"],
                     fg_color=self.styles["colors"]["success"], hover_color="#2b9348",
                     command=self.create_server).grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        ctk.CTkButton(btn_frame, text="Add Existing", font=self.styles["fonts"]["body"],
                     fg_color=self.styles["colors"]["primary"], hover_color=self.styles["colors"]["secondary"],
                     command=self.add_server).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
                     
        ctk.CTkButton(btn_frame, text="Edit Server", font=self.styles["fonts"]["body"],
                     fg_color=self.styles["colors"]["secondary"], hover_color=self.styles["colors"]["primary"],
                     command=self.edit_server).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
                     
        ctk.CTkButton(btn_frame, text="Delete", font=self.styles["fonts"]["body"],
                     fg_color=self.styles["colors"]["danger"], hover_color="#c1121f",
                     command=self.remove_server).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
                     
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.server_list_frame = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
        self.server_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,5))
        
        # Network UI Integration Area
        self.tunnel_bg_frame = ctk.CTkFrame(left_frame, fg_color=self.styles["colors"]["bg"], corner_radius=6)
        self.tunnel_bg_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # Row 1: Status & Button
        tunnel_top = ctk.CTkFrame(self.tunnel_bg_frame, fg_color="transparent")
        tunnel_top.pack(fill=tk.X, padx=5, pady=5)
        
        self.tunnel_status_lbl = ctk.CTkLabel(tunnel_top, text="Desconectado", text_color=self.styles["colors"]["text_muted"], font=self.styles["fonts"]["body"])
        self.tunnel_status_lbl.pack(side=tk.LEFT, padx=5)
        
        self.tunnel_toggle_btn = ctk.CTkButton(tunnel_top, text="Activar Red", width=100, font=self.styles["fonts"]["body"],
                                               fg_color=self.styles["colors"]["primary"],
                                               command=self.toggle_tunnel)
        self.tunnel_toggle_btn.pack(side=tk.RIGHT, padx=5)

        # Segmented Tabs
        self.info_tab_var = ctk.StringVar(value="Players")
        self.info_seg_btn = ctk.CTkSegmentedButton(left_frame, values=["Players", "Plugins"], 
                                                   variable=self.info_tab_var, command=self.switch_info_tab,
                                                   fg_color=self.styles["colors"]["bg"],
                                                   selected_color=self.styles["colors"]["primary"],
                                                   unselected_color=self.styles["colors"]["bg"])
        self.info_seg_btn.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.info_text_frame = ctk.CTkFrame(left_frame, fg_color=self.styles["colors"]["bg"], height=150)
        self.info_text_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))
        self.info_text_frame.pack_propagate(False)
        
        self.players_text = scrolledtext.ScrolledText(self.info_text_frame, bg=self.styles["colors"]["bg"], fg=self.styles["colors"]["text"], font=self.styles["fonts"]["body"], borderwidth=0, highlightthickness=0, state=tk.DISABLED)
        self.plugins_text = scrolledtext.ScrolledText(self.info_text_frame, bg=self.styles["colors"]["bg"], fg=self.styles["colors"]["text"], font=self.styles["fonts"]["body"], borderwidth=0, highlightthickness=0, state=tk.DISABLED)
        
        self.players_text.pack(fill=tk.BOTH, expand=True)

        # Configure log colors
        for txt_widget in [self.players_text, self.plugins_text]:
            txt_widget.tag_configure("info", foreground="#A8DADC")
            txt_widget.tag_configure("warn", foreground="#FFB703")
            txt_widget.tag_configure("error", foreground="#E63946")
            txt_widget.tag_configure("fatal", foreground="#D00000", font=self.styles["fonts"]["heading"])

        right_frame = ctk.CTkFrame(main_frame, fg_color=self.styles["colors"]["fg"], corner_radius=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10,0))

        # Centered IP display at the top of the console
        ip_header_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        ip_header_frame.pack(fill=tk.X, pady=(0, 0))
        
        self.public_ip_display = ctk.CTkButton(ip_header_frame, text="localhost", 
                                               font=self.styles["fonts"]["heading"], 
                                               fg_color="#242323", 
                                               text_color=self.styles["colors"]["text_muted"],
                                               hover_color="#242323",
                                               corner_radius=1,
                                               width=180, height=35,
                                               cursor="hand2",
                                               command=self.copy_ip)
        self.public_ip_display.pack(expand=True)
        
        def on_ip_enter(e):
            if "localhost" in self.public_ip_display.cget("text"):
                self.public_ip_display.configure(text_color="#ffffff")
            else:
                self.public_ip_display.configure(text_color="#00ff00") # Brillante cuando está activo

        def on_ip_leave(e):
            if "localhost" in self.public_ip_display.cget("text"):
                self.public_ip_display.configure(text_color=self.styles["colors"]["text_muted"])
            else:
                self.public_ip_display.configure(text_color=self.styles["colors"]["success"])

        self.public_ip_display.bind("<Enter>", on_ip_enter)
        self.public_ip_display.bind("<Leave>", on_ip_leave)

        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("TNotebook", background=self.styles["colors"]["fg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=self.styles["colors"]["bg"], foreground=self.styles["colors"]["text"], padding=[10, 2], font=self.styles["fonts"]["body"])
        style.map("TNotebook.Tab", background=[("selected", self.styles["colors"]["primary"])])
        
        self.console_notebook = ttk.Notebook(right_frame)
        self.console_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self.btn_frame_start = ctk.CTkFrame(right_frame, fg_color="transparent")
        self.btn_frame_start.pack(fill=tk.X, pady=5, padx=10)

        self.cmd_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        self.cmd_frame.pack(fill=tk.X, pady=(5,10), padx=10)
        
        ctk.CTkLabel(self.cmd_frame, text="Command:", font=self.styles["fonts"]["body"], text_color=self.styles["colors"]["text"]).pack(side=tk.LEFT, padx=(0,10))
        
        self.cmd_entry = ctk.CTkEntry(self.cmd_frame, font=self.styles["fonts"]["console"], 
                                     fg_color=self.styles["colors"]["bg"], text_color=self.styles["colors"]["text"],
                                     border_color=self.styles["colors"]["primary"])
        self.cmd_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.cmd_entry.bind('<Return>', self.send_global_command)
        
        ctk.CTkButton(self.cmd_frame, text="Send", font=self.styles["fonts"]["body"], width=80,
                     fg_color=self.styles["colors"]["primary"], hover_color=self.styles["colors"]["secondary"],
                     command=self.send_global_command).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(self.cmd_frame, text="Logs", font=self.styles["fonts"]["body"], width=60,
                     fg_color=self.styles["colors"]["secondary"], hover_color=self.styles["colors"]["primary"],
                     command=self.open_logs_folder).pack(side=tk.RIGHT, padx=(0,5))

        # Suggestion overlay (initially hidden)
        self.suggestion_frame = ctk.CTkFrame(right_frame, fg_color=self.styles["colors"]["bg"], 
                                            border_width=1, border_color=self.styles["colors"]["primary"],
                                            corner_radius=8)
        
        for cmd in self.suggestion_commands:
            btn = ctk.CTkButton(self.suggestion_frame, text=cmd, font=self.styles["fonts"]["body"],
                               fg_color="transparent", text_color=self.styles["colors"]["text"],
                               hover_color=self.styles["colors"]["primary"], height=25,
                               anchor="w", command=lambda c=cmd: self.insert_suggestion(c))
            btn.pack(fill=tk.X, padx=2, pady=1)

        self.cmd_entry.bind("<FocusIn>", lambda e: self.show_suggestions())
        self.cmd_entry.bind("<FocusOut>", lambda e: self.root.after(200, self.hide_suggestions))

        self.refresh_servers()

    def toggle_tunnel(self):
        if self.tunnel_controller.is_running:
            self.tunnel_controller.stop()
        else:
            self.tunnel_controller.start()

    def copy_ip(self):
        ip = self.public_ip_display.cget("text")
        if ip:
            self.root.clipboard_clear()
            self.root.clipboard_append(ip)
            messagebox.showinfo("Copiado", f"IP copiada exitosamente: {ip}")

    def open_network_config(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Configuración de Red Pública")
        dialog.geometry("450x450")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text="Preferencia de Túnel:").pack(anchor="w", padx=20, pady=(15, 0))
        pref_var = tk.StringVar(value=self.tunnel_controller.method_preference)
        ctk.CTkOptionMenu(dialog, variable=pref_var, values=["auto", "playit", "ngrok"], width=150).pack(anchor="w", padx=20, pady=5)
        
        ctk.CTkLabel(dialog, text="Timeout para Fallback (segundos):").pack(anchor="w", padx=20, pady=(10, 0))
        time_entry = ctk.CTkEntry(dialog, width=80)
        time_entry.insert(0, str(self.tunnel_controller.fallback_timeout))
        time_entry.pack(anchor="w", padx=20, pady=5)

        ctk.CTkLabel(dialog, text="Ngrok Authtoken (Requerido para TCP):").pack(anchor="w", padx=20, pady=(10, 0))
        token_entry = ctk.CTkEntry(dialog, width=350, show="*")
        token_entry.insert(0, self.tunnel_controller.ngrok_token)
        token_entry.pack(padx=20, pady=5)
        
        ctk.CTkLabel(dialog, text="Ruta Ejecutable de Playit (Opcional):").pack(anchor="w", padx=20, pady=(10, 0))
        playit_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        playit_frame.pack(fill=tk.X, padx=20, pady=5)
        p_entry = ctk.CTkEntry(playit_frame)
        p_entry.insert(0, self.tunnel_controller.playit_path)
        p_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ctk.CTkButton(playit_frame, text="Explorar", width=60, command=lambda: [p_entry.delete(0, tk.END), p_entry.insert(0, filedialog.askopenfilename(title="Seleccionar playit.exe"))]).pack(side=tk.RIGHT)
        
        ctk.CTkLabel(dialog, text="Ruta Ejecutable de Ngrok (Opcional):").pack(anchor="w", padx=20, pady=(10, 0))
        ngrok_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        ngrok_frame.pack(fill=tk.X, padx=20, pady=5)
        n_entry = ctk.CTkEntry(ngrok_frame)
        n_entry.insert(0, self.tunnel_controller.ngrok_path)
        n_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ctk.CTkButton(ngrok_frame, text="Explorar", width=60, command=lambda: [n_entry.delete(0, tk.END), n_entry.insert(0, filedialog.askopenfilename(title="Seleccionar ngrok.exe"))]).pack(side=tk.RIGHT)
        
        def save_config():
            try:
                to = int(time_entry.get().strip())
            except:
                to = 15
            self.tunnel_controller.save_config(
                p_entry.get().strip(),
                n_entry.get().strip(),
                token_entry.get().strip(),
                to,
                pref_var.get()
            )
            messagebox.showinfo("Guardado", "Configuración de Red guardada exitosamente.")
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Guardar Cambios", fg_color=self.styles["colors"]["primary"], hover_color=self.styles["colors"]["secondary"], command=save_config).pack(pady=20)

    def _on_tunnel_log(self, text_line):
        self.root.after(0, self._insert_tunnel_console, text_line + "\n")

    def _on_tunnel_status(self, status, ip_str):
        def update():
            self.tunnel_status_lbl.configure(text=status)
            
            # Button logic
            if "Desconectado" in status or "Error" in status:
                self.tunnel_toggle_btn.configure(text="Activar Red", fg_color=self.styles["colors"]["primary"])
            else:
                self.tunnel_toggle_btn.configure(text="Detener", fg_color=self.styles["colors"]["danger"])

            # Color logic
            if "Error" in status:
                self.tunnel_status_lbl.configure(text_color=self.styles["colors"]["danger"])
            elif "Activo" in status:
                self.tunnel_status_lbl.configure(text_color=self.styles["colors"]["success"])
            elif "Autenticación" in status or "Fallback" in status:
                self.tunnel_status_lbl.configure(text_color="#ffb703") # Orange
            else:
                self.tunnel_status_lbl.configure(text_color=self.styles["colors"]["text_muted"])

            # IP logic
            self._update_ip_display(ip_str)
            
        self.root.after(0, update)

    def _update_ip_display(self, ip_str=None):
        if not ip_str and self.tunnel_controller.is_running and self.tunnel_controller.active_tunnel:
            ip_str = self.tunnel_controller.active_tunnel.public_ip
            
        if ip_str:
            self.public_ip_display.configure(text=ip_str, text_color=self.styles["colors"]["success"])
        else:
            port_text = ""
            if self.selected_server:
                port = self.get_server_port(self.selected_server)
                port_text = f":{port}"
            self.public_ip_display.configure(text=f"localhost{port_text}", text_color=self.styles["colors"]["text_muted"])

    def _insert_tunnel_console(self, line):
        self.log_queue.put(("TUNNEL_SYSTEM", line))

    def update_ui_logs(self):
        """Batch update console logs from the queue every 100ms."""
        try:
            # Process up to 50 lines at a time to avoid blocking
            for _ in range(100): 
                try:
                    path_key, line = self.log_queue.get_nowait()
                    console_tab = self.get_or_create_console_tab(path_key)
                    self._insert_console_line(console_tab, line)
                    self.log_queue.task_done()
                except queue.Empty:
                    break
        finally:
            self.root.after(100, self.update_ui_logs)

    def switch_info_tab(self, tab_name=None):
        if not tab_name:
            tab_name = self.info_tab_var.get()
        self.players_text.pack_forget()
        self.plugins_text.pack_forget()
        if tab_name == "Players":
            self.players_text.pack(fill=tk.BOTH, expand=True)
        elif tab_name in ["Plugins", "Mods"]:
            self.plugins_text.pack(fill=tk.BOTH, expand=True)

    def refresh_servers(self):
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()

        for path_key, data in self.servers.items():
            is_running = path_key in self.server_processes
            status_color = self.styles["colors"]["success"] if is_running else self.styles["colors"]["danger"]
            bg_color = self.styles["colors"]["secondary"] if path_key == self.selected_server else self.styles["colors"]["bg"]
            
            name = data.get("name", "Unknown Server")
            version = data.get("version", "Vanilla")

            card = ctk.CTkFrame(self.server_list_frame, fg_color=bg_color, corner_radius=8, cursor="hand2")
            card.pack(fill=tk.X, pady=5, padx=5)

            text_frame = ctk.CTkFrame(card, fg_color="transparent")
            text_frame.pack(pady=(12, 8), expand=True)
            
            name_lbl = ctk.CTkLabel(text_frame, text=name, font=self.styles["fonts"]["heading"], text_color=self.styles["colors"]["text"])
            name_lbl.pack()
            
            ver_lbl = ctk.CTkLabel(text_frame, text=f"v{version}", font=self.styles["fonts"]["body"], text_color=self.styles["colors"]["text_muted"])
            ver_lbl.pack()

            status_line = ctk.CTkFrame(card, fg_color=status_color, height=4, corner_radius=0)
            status_line.pack(fill=tk.X, side=tk.BOTTOM)

            card.bind("<Button-1>", lambda e, p=path_key: self.on_server_select(p))
            name_lbl.bind("<Button-1>", lambda e, p=path_key: self.on_server_select(p))
            ver_lbl.bind("<Button-1>", lambda e, p=path_key: self.on_server_select(p))
            status_line.bind("<Button-1>", lambda e, p=path_key: self.on_server_select(p))
            text_frame.bind("<Button-1>", lambda e, p=path_key: self.on_server_select(p))

            card.bind("<Button-3>", lambda e, p=path_key: self._show_server_context_menu(e, p))
            name_lbl.bind("<Button-3>", lambda e, p=path_key: self._show_server_context_menu(e, p))
            ver_lbl.bind("<Button-3>", lambda e, p=path_key: self._show_server_context_menu(e, p))
            status_line.bind("<Button-3>", lambda e, p=path_key: self._show_server_context_menu(e, p))
            text_frame.bind("<Button-3>", lambda e, p=path_key: self._show_server_context_menu(e, p))

    def _show_server_context_menu(self, event, path_key):
        # Auto-select server first so the user sees which one they clicked
        self.on_server_select(path_key)
        
        menu = tk.Menu(self.root, tearoff=0, bg=self.styles["colors"]["bg"], fg=self.styles["colors"]["text"])
        menu.add_command(label="Abrir Ubicación", command=lambda: os.startfile(path_key) if os.name == 'nt' else subprocess.call(["xdg-open", path_key]))
        menu.add_separator()
        menu.add_command(label="Editar Servidor", command=self.edit_server)
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def create_server(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Install New Server")
        dialog.geometry("480x550")
        dialog.transient(self.root)
        dialog.grab_set()

        name_var = tk.StringVar(value="My New Server")
        loc_var = tk.StringVar()
        type_var = tk.StringVar(value="Paper")
        ver_var = tk.StringVar(value="1.20.4")
        ram_var = tk.StringVar(value="4G")
        java_var = tk.StringVar(value="java")

        wrapper = ctk.CTkFrame(dialog, fg_color="transparent")
        wrapper.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(wrapper, text="Server Name / Folder Name:").pack(anchor="w")
        ctk.CTkEntry(wrapper, textvariable=name_var).pack(fill=tk.X, pady=(0, 10))

        ctk.CTkLabel(wrapper, text="Install Location:").pack(anchor="w")
        loc_frame = ctk.CTkFrame(wrapper, fg_color="transparent")
        loc_frame.pack(fill=tk.X, pady=(0, 10))
        ctk.CTkEntry(loc_frame, textvariable=loc_var, state="disabled").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ctk.CTkButton(loc_frame, text="Browse", width=60, command=lambda: loc_var.set(filedialog.askdirectory())).pack(side=tk.RIGHT)

        row_frame1 = ctk.CTkFrame(wrapper, fg_color="transparent")
        row_frame1.pack(fill=tk.X, pady=(0, 10))
        
        ctk.CTkLabel(row_frame1, text="Type:").grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(row_frame1, variable=type_var, values=["Paper", "Vanilla", "Forge"], width=150).grid(row=1, column=0, sticky="w", padx=(0,10))
        
        ctk.CTkLabel(row_frame1, text="Minecraft Version:").grid(row=0, column=1, sticky="w")
        ver_menu = ctk.CTkOptionMenu(row_frame1, variable=ver_var, values=["1.21.1", "1.20.4", "1.19.4", "1.18.2", "1.16.5", "1.12.2"], width=150)
        ver_menu.grid(row=1, column=1, sticky="w")

        row_frame2 = ctk.CTkFrame(wrapper, fg_color="transparent")
        row_frame2.pack(fill=tk.X, pady=(0, 10))
        
        ctk.CTkLabel(row_frame2, text="RAM (e.g., 4G):").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(row_frame2, textvariable=ram_var, width=150).grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(wrapper, text="Java Executable Path (Default: 'java'):").pack(anchor="w")
        java_frame = ctk.CTkFrame(wrapper, fg_color="transparent")
        java_frame.pack(fill=tk.X, pady=(0, 5))
        ctk.CTkEntry(java_frame, textvariable=java_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ctk.CTkButton(java_frame, text="Browse", width=60, command=lambda: java_var.set(filedialog.askopenfilename(title="Select java.exe"))).pack(side=tk.RIGHT)
        
        java_hint_lbl = ctk.CTkLabel(wrapper, text="Hint: Versions 1.17+ require Java 17+. Versions <= 1.16 require Java 8.", font=self.styles["fonts"]["body"], text_color=self.styles["colors"]["primary"])
        java_hint_lbl.pack(anchor="w", pady=(0, 15))

        def update_hint(*args):
            v = ver_var.get()
            if v in ["1.16.5", "1.12.2"]:
                java_hint_lbl.configure(text=f"WARNING: {v} typically requires Java 8! Pick your Java 8 path.", text_color=self.styles["colors"]["danger"])
            else:
                java_hint_lbl.configure(text=f"Hint: {v} usually requires Java 17 or 21.", text_color=self.styles["colors"]["primary"])
                
        ver_var.trace_add("write", update_hint)

        status_lbl = ctk.CTkLabel(wrapper, text="", text_color=self.styles["colors"]["text_muted"])
        status_lbl.pack(pady=5)
        
        create_btn = ctk.CTkButton(wrapper, text="Download & Create", fg_color=self.styles["colors"]["success"], hover_color="#2b9348")
        create_btn.pack(pady=10, fill=tk.X)

        def download_and_setup(name, loc, server_type, ver, ram, java_path, dialog_window):
            try:
                target_folder = Path(loc) / name
                target_folder.mkdir(parents=True, exist_ok=False)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create folder: {e}")
                create_btn.configure(state="normal", text="Download & Create")
                status_lbl.configure(text="Error creating directory.")
                return

            target_jar = target_folder / "server.jar"
            
            try:
                if server_type == "Paper":
                    status_lbl.configure(text="Fetching Paper API...")
                    url = f"https://api.papermc.io/v2/projects/paper/versions/{ver}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as resp:
                        data = json.loads(resp.read().decode())
                        latest_build = data["builds"][-1]
                    
                    dl_url = f"https://api.papermc.io/v2/projects/paper/versions/{ver}/builds/{latest_build}/downloads/paper-{ver}-{latest_build}.jar"
                    status_lbl.configure(text="Downloading Paper Jar...")
                    req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as resp, open(target_jar, 'wb') as f:
                        shutil.copyfileobj(resp, f)

                elif server_type == "Vanilla":
                    status_lbl.configure(text="Fetching Mojang API...")
                    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
                    with urllib.request.urlopen(manifest_url) as resp:
                        manifest = json.loads(resp.read().decode())
                    
                    version_url = None
                    for v in manifest.get("versions", []):
                        if v["id"] == ver:
                            version_url = v["url"]
                            break
                            
                    if not version_url:
                        raise Exception("Vanilla version manifest not found.")

                    with urllib.request.urlopen(version_url) as resp:
                        v_data = json.loads(resp.read().decode())
                        if "server" not in v_data.get("downloads", {}):
                            raise Exception("No server assigned to this vanilla version.")
                        dl_url = v_data["downloads"]["server"]["url"]
                        
                    status_lbl.configure(text="Downloading Vanilla Jar...")
                    with urllib.request.urlopen(dl_url) as resp, open(target_jar, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                        
                elif server_type == "Forge":
                    status_lbl.configure(text="Targeting Forge Maven...")
                    FORGE_VERSIONS = {
                        "1.21.1": "51.0.32",
                        "1.20.4": "49.0.50",
                        "1.19.4": "45.3.3",
                        "1.18.2": "40.2.18",
                        "1.16.5": "36.2.39",
                        "1.12.2": "14.23.5.2860"
                    }
                    if ver not in FORGE_VERSIONS:
                        raise Exception(f"Forge auto-installer not supported for version {ver}.")
                        
                    forge_ver = FORGE_VERSIONS[ver]
                    installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{ver}-{forge_ver}/forge-{ver}-{forge_ver}-installer.jar"
                    installer_jar = target_folder / "installer.jar"
                    
                    status_lbl.configure(text=f"Downloading Forge Installer...")
                    req = urllib.request.Request(installer_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as resp, open(installer_jar, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                        
                    status_lbl.configure(text="Running Forge Auto-Installer (Please wait)...")
                    cmd = [java_path, "-jar", str(installer_jar), "--installServer"]
                    subprocess.run(cmd, cwd=str(target_folder), capture_output=True, check=True)
                    
                    try:
                        installer_jar.unlink(missing_ok=True)
                        (target_folder / "installer.jar.log").unlink(missing_ok=True)
                    except: pass
                    
                    run_bat = target_folder / "run.bat"
                    if run_bat.exists():
                        args_file = target_folder / "user_jvm_args.txt"
                        if args_file.exists():
                            args_text = args_file.read_text()
                            if f"-Xmx{ram}" not in args_text:
                                args_text += f"\n-Xms{ram} -Xmx{ram}\n"
                                args_file.write_text(args_text)
                        if args_file.exists():
                            args_mod = f'"{java_path}" @user_jvm_args.txt @libraries/net/minecraftforge/forge/{ver}-{forge_ver}/win_args.txt nogui\n'
                            (target_folder / "start.bat").write_text(args_mod)
                        else:
                            (target_folder / "start.bat").write_text("call run.bat\n")
                    else:
                        legacy_jars = list(target_folder.glob(f"forge-{ver}-*.jar"))
                        if legacy_jars:
                            legacy_jars[0].rename(target_jar)
                        else:
                            raise Exception("Could not locate the installed Forge server jar.")
                    
            except Exception as e:
                messagebox.showerror("Install Error", str(e))
                shutil.rmtree(target_folder, ignore_errors=True)
                def reset_ui():
                    if dialog_window.winfo_exists():
                        create_btn.configure(state="normal", text="Download & Create")
                        status_lbl.configure(text="Installation failed.")
                self.root.after(0, reset_ui)
                return

            status_lbl.configure(text="Writing Configuration...")
            (target_folder / "eula.txt").write_text("eula=true\n")
            if not (target_folder / "start.bat").exists():
                (target_folder / "start.bat").write_text(f'"{java_path}" -Xmx{ram} -Xms{ram} -jar server.jar nogui\n')

            self.root.after(0, finalize_creation, target_folder, name, ver, java_path, server_type, dialog_window)

        def finalize_creation(target_folder, name, ver, java_path, server_type, dialog_window):
            path_key = str(target_folder.absolute())
            self.servers[path_key] = {"name": name, "version": ver, "java_path": java_path, "type": server_type}
            self.save_servers()
            self.refresh_servers()
            self.on_server_select(path_key)
            if dialog_window.winfo_exists():
                dialog_window.destroy()
            messagebox.showinfo("Success", f"Server '{name}' automatically installed and created successfully!")

        def submit():
            name = name_var.get().strip()
            loc = loc_var.get().strip()
            server_type = type_var.get()
            ver = ver_var.get().strip()
            ram = ram_var.get().strip()
            java_path = java_var.get().strip()
            
            if not java_path:
                java_path = "java"

            if not all([name, loc, ver, ram]):
                messagebox.showerror("Error", "Please fill all fields, including the install location.")
                return
                
            create_btn.configure(state="disabled", text="Working...")
            threading.Thread(target=download_and_setup, args=(name, loc, server_type, ver, ram, java_path, dialog), daemon=True).start()

        create_btn.configure(command=submit)

    def add_server(self):
        folder_path = filedialog.askdirectory(title="Select Server Folder")
        if not folder_path:
            return
        
        path_key = str(Path(folder_path).absolute())
        
        if path_key in self.servers:
            messagebox.showerror("Error", "Server path already added")
            return

        jar_files = list(Path(folder_path).glob("*.jar"))
        bat_files = list(Path(folder_path).glob("*.bat"))
        if not jar_files and not bat_files:
            messagebox.showerror("Error", "No server.jar or start.bat found")
            return

        folder_name = os.path.basename(folder_path)
        
        if (Path(folder_path) / "mods").exists(): s_type = "Forge"
        elif (Path(folder_path) / "plugins").exists(): s_type = "Paper"
        else: s_type = "Vanilla"
        
        self.servers[path_key] = {"name": folder_name, "version": "Unknown", "java_path": "java", "type": s_type}
        self.save_servers()
        self.refresh_servers()

    def edit_server(self):
        if not self.selected_server:
            messagebox.showinfo("Select Server", "Please select a server to edit.")
            return

        data = self.servers[self.selected_server]
        
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Edit Server")
        dialog.geometry("380x300")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Server Name:").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(dialog, width=250)
        name_entry.insert(0, data.get("name", ""))
        name_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="Server Version:").pack(pady=(10, 0))
        ver_entry = ctk.CTkEntry(dialog, width=250)
        ver_entry.insert(0, data.get("version", ""))
        ver_entry.pack(pady=5)
        
        ctk.CTkLabel(dialog, text="Java Path (Default: 'java'):").pack(pady=(10, 0))
        java_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        java_frame.pack(fill=tk.X, pady=5, padx=20)
        java_entry = ctk.CTkEntry(java_frame)
        java_entry.insert(0, data.get("java_path", "java"))
        java_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))
        ctk.CTkButton(java_frame, text="Browse", width=60, command=lambda: [java_entry.delete(0, tk.END), java_entry.insert(0, filedialog.askopenfilename(title="Select java.exe"))]).pack(side=tk.RIGHT)

        def save_changes():
            self.servers[self.selected_server]["name"] = name_entry.get()
            self.servers[self.selected_server]["version"] = ver_entry.get()
            jval = java_entry.get().strip()
            self.servers[self.selected_server]["java_path"] = jval if jval else "java"
            self.save_servers()
            self.refresh_servers()
            if self.selected_server in self.console_tabs_index:
                tab_id = self.console_tabs_index[self.selected_server]
                self.console_notebook.tab(tab_id, text=name_entry.get())
            dialog.destroy()

        ctk.CTkButton(dialog, text="Save", command=save_changes, fg_color=self.styles["colors"]["primary"], hover_color=self.styles["colors"]["secondary"]).pack(pady=15)

    def remove_server(self):
        if not self.selected_server:
            return
            
        path_key = self.selected_server
        data = self.servers[path_key]
        name = data.get("name", "Unknown")
        
        confirm = messagebox.askyesno("Delete Server", 
                                      f"Are you sure you want to completely delete '{name}' and ALL its files from your PC?\n\nThis action cannot be cleanly reversed.",
                                      icon='warning')
        if not confirm:
            return
            
        try:
            shutil.rmtree(path_key, ignore_errors=True)
        except Exception as e:
            messagebox.showwarning("Warning", f"Could not fully delete the folder from disk exactly. Some files might have been in use: {e}")
            
        del self.servers[path_key]
        self.save_servers()
        if path_key in self.server_processes:
            self.stop_server(path_key)
        self.selected_server = None
        self.refresh_servers()
        self.clear_info_panels()

    def clear_info_panels(self):
        self._update_text_widget(self.plugins_text, "")
        self._update_text_widget(self.players_text, "")

    def _update_text_widget(self, widget, text):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state=tk.DISABLED)

    def on_server_select(self, path_key):
        self.selected_server = path_key
        self.refresh_servers()

        for widget in self.btn_frame_start.winfo_children():
            widget.destroy()

        if path_key in self.server_processes:
            ctk.CTkButton(self.btn_frame_start, text="Stop Server", font=self.styles["fonts"]["heading"],
                         fg_color=self.styles["colors"]["danger"], hover_color="#c1121f",
                         command=lambda: self.stop_server(path_key)).pack(fill=tk.X, expand=True)
        else:
            ctk.CTkButton(self.btn_frame_start, text="Start Server", font=self.styles["fonts"]["heading"],
                         fg_color=self.styles["colors"]["success"], hover_color="#2b9348",
                         command=lambda: self.start_server(path_key)).pack(fill=tk.X, expand=True)

        if path_key in self.console_tabs_index:
            self.console_notebook.select(self.console_tabs_index[path_key])
            
        server_type = self.servers[path_key].get("type", "Vanilla")
        
        if server_type == "Forge":
            self.info_seg_btn.configure(values=["Players", "Mods"])
            if self.info_tab_var.get() == "Plugins":
                self.info_tab_var.set("Mods")
        else:
            self.info_seg_btn.configure(values=["Players", "Plugins"])
            if self.info_tab_var.get() == "Mods":
                self.info_tab_var.set("Plugins")
            
        self.update_plugins_list(path_key, server_type)
        self.update_players_list(path_key)
        self._update_ip_display()
        
        self.switch_info_tab()

    def update_plugins_list(self, path_key, server_type):
        if not path_key:
            return
            
        target_dir_name = "mods" if server_type == "Forge" else "plugins"
        target_dir = Path(path_key) / target_dir_name
        
        self.plugins_text.config(state=tk.NORMAL)
        self.plugins_text.delete("1.0", tk.END)
        
        # Ensure styles are configured
        self.plugins_text.tag_configure("version", font=(self.styles["fonts"]["body"][0], 8), foreground=self.styles["colors"]["text_muted"])
        self.plugins_text.tag_configure("online", foreground=self.styles["colors"]["success"])
        self.plugins_text.tag_configure("offline", foreground=self.styles["colors"]["danger"])
        self.plugins_text.tag_configure("info", foreground=self.styles["colors"]["text"])

        found_any = False
        if target_dir.exists() and target_dir.is_dir():
            jar_files = list(target_dir.glob("*.jar"))
            if jar_files:
                self.plugins_text.insert(tk.END, f"Found {len(jar_files)} {target_dir_name.capitalize()}:\n\n")
                found_any = True
                
                for jar in jar_files:
                    name = jar.stem
                    version = "???"
                    internal_name = None
                    
                    # Try metadata if possible
                    if zipfile:
                        try:
                            with zipfile.ZipFile(jar, 'r') as z:
                                if server_type == "Forge" and "mods.toml" in z.namelist():
                                    with z.open("mods.toml") as f:
                                        content = f.read().decode('utf-8', errors='ignore')
                                        disp_match = re.search(r'displayName="([^"]+)"', content)
                                        ver_match = re.search(r'version="([^"]+)"', content)
                                        if disp_match: 
                                            name = disp_match.group(1)
                                            internal_name = name
                                        if ver_match: version = ver_match.group(1)
                                elif "plugin.yml" in z.namelist():
                                    with z.open("plugin.yml") as f:
                                        if yaml:
                                            try:
                                                yml = yaml.safe_load(f)
                                                name = yml.get("name", name)
                                                internal_name = name
                                                version = str(yml.get("version", version))
                                            except: pass
                                        
                                        # Fallback regex search if yaml fails or isn't available
                                        if version == "???":
                                            f.seek(0)
                                            content = f.read().decode('utf-8', errors='ignore')
                                            n_m = re.search(r'name:\s*([^\s\n\"\'\#]+)', content)
                                            v_m = re.search(r'version:\s*([^\s\n\"\'\#]+)', content)
                                            if n_m: 
                                                name = n_m.group(1).strip("\"' ")
                                                internal_name = name
                                            if v_m: version = v_m.group(1).strip("\"' ")
                        except: pass
                    
                    # Insert name and version
                    self.plugins_text.insert(tk.END, f"• {name} ", "info")
                    self.plugins_text.insert(tk.END, f" v{version}\n", "version")
        
        if not found_any:
            self.plugins_text.insert(tk.END, f"No {target_dir_name} found or Vanilla server.")
            
        self.plugins_text.config(state=tk.DISABLED)

    def update_players_list(self, path_key):
        if path_key not in self.active_players:
            self.active_players[path_key] = set()
            
        players = self.active_players[path_key]
        if not players:
            txt = "No players currently online."
        else:
            txt = f"Online ({len(players)}):\n\n" + "\n".join(f"• {p}" for p in players)
            
        self._update_text_widget(self.players_text, txt)

    def start_server(self, path_key):
        port = self.get_server_port(path_key)
        if self.is_port_in_use(port):
            messagebox.showerror("Puerto Ocupado", f"El puerto {port} del servidor ya está en uso.\n\nEs probable que otro servidor o aplicación lo esté utilizando actualmente. Debes apagar el proceso anterior o cambiar el puerto en server.properties primero.")
            return

        start_file = None
        bat_path = Path(path_key) / "start.bat"
        javap = self.servers.get(path_key, {}).get("java_path", "java").strip("\"' ")
        
        # If we have a start.bat, we try to run it, but we'll try to hide it.
        if bat_path.exists():
            # If it's a batch file, we can try to run it with nogui if it's a jar line
            start_file = str(bat_path)
            # Check if it has nogui
            try:
                content = bat_path.read_text()
                if "nogui" not in content.lower() and ".jar" in content.lower():
                    # Create a temporary 'silent' launch command to avoid modifying their file
                    jar_match = re.search(r'-jar\s+([^\s]+\.jar)', content)
                    if jar_match:
                        jar_name = jar_match.group(1)
                        # We build our own command to ensure nogui and correct java path
                        start_cmd = [javap, "-Xmx4G", "-Xms4G", "-jar", jar_name, "nogui"]
                        start_file = start_cmd
            except: pass
        else:
            jar_files = list(Path(path_key).glob("*.jar"))
            if jar_files:
                start_cmd = [javap, "-Xmx4G", "-Xms4G", "-jar", jar_files[0].name, "nogui"]
                start_file = start_cmd

        if not start_file:
            messagebox.showerror("Error", "No se pudo encontrar start.bat o un archivo .jar para iniciar el servidor.")
            return

        try:
            # Clear console before starting
            con = self.get_or_create_console_tab(path_key)
            con.config(state=tk.NORMAL)
            con.delete("1.0", tk.END)
            con.config(state=tk.DISABLED)

            # Ensure we use list for subprocess if it's a direct command
            process = subprocess.Popen(
                start_file,
                cwd=path_key,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                creationflags=CREATE_NO_WINDOW
            )
                
            self.server_processes[path_key] = process
            self.active_players[path_key] = set()

            thread = threading.Thread(target=self.read_console, args=(path_key, process.stdout), daemon=True)
            thread.start()

            self.refresh_servers()
            self.on_server_select(path_key)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_server(self, path_key):
        if path_key not in self.server_processes:
            return
            
        process = self.server_processes[path_key]
        
        def attempt_stop():
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
                # Wait a bit for graceful stop
                process.wait(timeout=3)
                self.root.after(0, self._finalize_stop, path_key)
            except subprocess.TimeoutExpired:
                # If it didn't stop in 3s, ask the user
                self.root.after(0, self._ask_force_kill, path_key)
            except Exception as e:
                # Pipe might be broken if it already crashed
                self.root.after(0, self._finalize_stop, path_key)

        threading.Thread(target=attempt_stop, daemon=True).start()

    def _ask_force_kill(self, path_key):
        if path_key not in self.server_processes:
            return
            
        confirm = messagebox.askyesno(
            "Servidor no responde",
            "El servidor no ha respondido al comando de apagado (posiblemente aún está iniciando o se ha congelado).\n\n"
            "¿Deseas FORZAR el cierre (Kill)?\nEsto cerrará el proceso de golpe y podría corromper el mundo si no se ha guardado.",
            icon='warning'
        )
        
        if confirm:
            try:
                process = self.server_processes[path_key]
                if os.name == 'nt':
                    # Use taskkill to kill the entire process tree (/T) including Java children
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], 
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.kill()
            except: pass
            self._finalize_stop(path_key)

    def _finalize_stop(self, path_key):
        if path_key in self.server_processes:
            del self.server_processes[path_key]
            self.active_players[path_key] = set()
            self.refresh_servers()
            self.on_server_select(path_key)

    def parse_console_for_players(self, path_key, line):
        # Existing player tracking
        join_match = self.player_join_pattern.search(line)
        if join_match:
            player = join_match.group(1)
            self.active_players[path_key].add(player)
            if self.selected_server == path_key:
                self.root.after(0, self.update_players_list, path_key)
                
        leave_match = self.player_leave_pattern.search(line)
        if leave_match:
            player = leave_match.group(1)
            if player in self.active_players[path_key]:
                self.active_players[path_key].remove(player)
            if self.selected_server == path_key:
                self.root.after(0, self.update_players_list, path_key)

    def read_console(self, path_key, stdout):
        while True:
            line = stdout.readline()
            if not line:
                break
            
            self.parse_console_for_players(path_key, line)
            self.log_queue.put((path_key, line))
            
    def _insert_console_line(self, console_tab, line):
        tag = None
        if self.log_patterns["fatal"].search(line): tag = "fatal"
        elif self.log_patterns["error"].search(line): tag = "error"
        elif self.log_patterns["warn"].search(line): tag = "warn"
        elif self.log_patterns["info"].search(line): tag = "info"
        
        console_tab.config(state=tk.NORMAL)
        if tag:
            console_tab.insert(tk.END, line, tag)
        else:
            console_tab.insert(tk.END, line)
        console_tab.see(tk.END)
        console_tab.config(state=tk.DISABLED)

    def get_or_create_console_tab(self, path_key, is_tunnel=False):
        if path_key not in self.server_consoles:
            console_frame = ctk.CTkFrame(self.console_notebook, fg_color=self.styles["colors"]["bg"])
            if is_tunnel:
                name = "Public Network"
            else:
                name = self.servers.get(path_key, {}).get("name", "Unknown Server")
            self.console_notebook.add(console_frame, text=name)
            self.console_tabs_index[path_key] = self.console_notebook.index(console_frame)
            console_text = scrolledtext.ScrolledText(console_frame, height=15, 
                                                     bg=self.styles["colors"]["bg"], 
                                                     fg=self.styles["colors"]["text"],
                                                     font=self.styles["fonts"]["console"],
                                                     insertbackground=self.styles["colors"]["text"],
                                                     borderwidth=0, highlightthickness=0)
            console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Configure tags for this specific widget as well
            console_text.tag_configure("info", foreground="#A8DADC")
            console_text.tag_configure("warn", foreground="#FFB703")
            console_text.tag_configure("error", foreground="#E63946")
            console_text.tag_configure("fatal", foreground="#D00000", font=self.styles["fonts"]["heading"])
            
            self.server_consoles[path_key] = console_text
        return self.server_consoles[path_key]

    def send_global_command(self, event=None):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        running_servers = [p for p in self.server_processes.keys()]
        if running_servers:
            target = self.selected_server if self.selected_server in self.server_processes else running_servers[0]
            self.server_processes[target].stdin.write(cmd + "\n")
            self.server_processes[target].stdin.flush()
            self._insert_console_line(self.server_consoles[target], f"> {cmd}\n")
        self.cmd_entry.delete(0, tk.END)

    def open_logs_folder(self):
        if not self.selected_server:
            messagebox.showinfo("Logs", "Por favor selecciona un servidor primero.")
            return
            
        logs_path = Path(self.selected_server) / "logs"
        if not logs_path.exists():
            try:
                logs_path.mkdir(parents=True, exist_ok=True)
            except: pass
            
        if os.name == 'nt':
            os.startfile(logs_path)
        else:
            subprocess.call(["xdg-open", str(logs_path)])

    def show_suggestions(self):
        if self.suggestion_frame:
            # Place it above the command frame
            self.suggestion_frame.place(relx=0.5, rely=0.88, anchor="s", relwidth=0.9)
            self.suggestion_frame.lift()

    def hide_suggestions(self):
        if self.suggestion_frame:
            self.suggestion_frame.place_forget()

    def insert_suggestion(self, cmd):
        self.cmd_entry.delete(0, tk.END)
        self.cmd_entry.insert(0, cmd)
        self.cmd_entry.focus_set()
        self.hide_suggestions()

if __name__ == "__main__":
    root = ctk.CTk()
    app = MinecraftLauncher(root)
    root.mainloop()
