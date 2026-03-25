import subprocess
import threading
import json
import re
import os
import shutil
import time
from pathlib import Path

class PlayitManager:
    def __init__(self, data_dir, on_log=None, on_status_change=None):
        self.config_path = Path(data_dir) / "playit_settings.json"
        self.playit_path = "playit.exe" if os.name == 'nt' else "playit"
        
        self.process = None
        self.running = False
        self.public_ip = None
        self.status = "No conectado"
        
        self.on_log = on_log
        self.on_status_change = on_status_change # callback(status, ip)
        
        self.load_config()

    def load_config(self):
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                self.playit_path = data.get("playit_path", self.playit_path)
            except: pass

    def save_config(self, playit_path=None):
        if playit_path is not None:
            self.playit_path = playit_path
        self.config_path.write_text(json.dumps({
            "playit_path": self.playit_path
        }, indent=4))

    def is_installed(self):
        return shutil.which(self.playit_path) is not None or Path(self.playit_path).exists()

    def update_status(self, status, ip=None):
        self.status = status
        if ip is not None:
            self.public_ip = ip
        if self.on_status_change:
            self.on_status_change(self.status, self.public_ip)

    def set_callbacks(self, on_log, on_status_change):
        self.on_log = on_log
        self.on_status_change = on_status_change

    def start(self):
        if self.running: return True
        if not self.is_installed():
            self.update_status("Error", None)
            if self.on_log: self.on_log(f"[Playit Error] El ejecutable no fue encontrado en '{self.playit_path}'.")
            return False

        self.running = True
        self.update_status("Conectando", None)
        threading.Thread(target=self._run_loop, daemon=True).start()
        return True

    def _run_loop(self):
        while self.running:
            try:
                if self.on_log: self.on_log("[Playit] Iniciando proceso...")
                
                # Ejecutar playit directamente. Si no hay config, abrirá el navegador automáticamente.
                cmd = [self.playit_path]
                
                creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    creationflags=creation_flags
                )
                
                buffer = ""
                while self.running:
                    char = self.process.stdout.read(1)
                    if not char:
                        break
                    
                    if char != '\r':
                        buffer += char
                    
                    # Process completed line
                    if buffer.endswith("\n"):
                        line = buffer.strip()
                        if line and self.on_log:
                            self.on_log(f"[Playit] {line}")
                            
                        if "https://playit.gg/claim/" in line:
                            self.update_status("Esperando Autenticación", None)
                            
                        match = re.search(r'([a-zA-Z0-9-]+\.(?:playit\.gg|auto\.playit\.gg):\d+)', line)
                        if match:
                            ip = match.group(1)
                            if self.public_ip != ip or self.status != "Activo":
                                self.update_status("Activo", ip)
                        buffer = ""
                    else:
                        # Process partial interactive prompts that lack line-endings
                        lower_buf = buffer.lower()
                        if lower_buf.endswith("? ") or "y/n" in lower_buf or "yes/no" in lower_buf or "yes or no" in lower_buf:
                            if self.on_log: self.on_log(f"[Playit Prompt] {buffer}")
                            try:
                                self.process.stdin.write("yes\n")
                                self.process.stdin.flush()
                            except: pass
                            buffer = ""
                        elif "https://playit.gg/claim/" in buffer and len(buffer.split("claim/")[1]) > 5:
                            if self.on_log: self.on_log(f"[Playit Setup] {buffer}")
                            self.update_status("Esperando Autenticación", None)
                            buffer = ""
                
                if self.process:
                    self.process.wait()
                    
            except Exception as e:
                if self.on_log: self.on_log(f"[Playit System Error] {e}")
                self.update_status("Error", None)
                
            if self.running:
                if self.on_log: self.on_log("[Playit] Proceso terminado. Reiniciando en 5 segundos...")
                self.update_status("Conectando", None)
                time.sleep(5)

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except: pass
            self.process = None
            
        self.update_status("No conectado", None)
        if self.on_log:
            self.on_log("[Playit] Túnel detenido.")
