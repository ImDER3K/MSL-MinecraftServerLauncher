import subprocess
import threading
import json
import os
import time
import shutil
from pathlib import Path

class BaseTunnel:
    def __init__(self, executable_path, name, on_log=None, on_status=None):
        self.executable_path = executable_path
        self.name = name
        self.process = None
        self.running = False
        self.public_ip = None
        self.on_log = on_log
        self.on_status = on_status # (status_string, ip_string)

    def is_installed(self):
        return shutil.which(self.executable_path) is not None or Path(self.executable_path).exists()

    def update_status(self, status, ip=None):
        if ip is not None:
            self.public_ip = ip
        if self.on_status:
            self.on_status(status, self.public_ip)

    def start(self):
        raise NotImplementedError
        
    def _safe_run(self, target):
        threading.Thread(target=target, daemon=True).start()

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.kill()
            except: pass
            self.process = None


class PlayitTunnel(BaseTunnel):
    def start(self):
        if self.running: return True
        if not self.is_installed(): return False
        self.running = True
        self._safe_run(self._run_loop)
        return True

    def _run_loop(self):
        try:
            import re
            ip_pattern = re.compile(r'([a-zA-Z0-9-]+\.(?:playit\.gg|auto\.playit\.gg):\d+)')
            
            cmd = [self.executable_path]
            import os
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
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.running: break
                line = line.strip()
                if not line: continue
                
                if self.on_log: self.on_log(f"[{self.name}] {line}")
                
                if "https://playit.gg/claim/" in line:
                    self.update_status("Esperando Autenticación", None)
                    
                match = ip_pattern.search(line)
                if match:
                    self.update_status("Activo", match.group(1))
                
                # Check for prompt
                lower_line = line.lower()
                if "? " in lower_line or "y/n" in lower_line or "yes/no" in lower_line:
                    try:
                        self.process.stdin.write("yes\n")
                        self.process.stdin.flush()
                    except: pass
                        
            if self.process: self.process.wait()
        except Exception as e:
            if self.on_log: self.on_log(f"[{self.name} Error] {e}")


class NgrokTunnel(BaseTunnel):
    def __init__(self, executable_path, name, authtoken="", on_log=None, on_status=None):
        super().__init__(executable_path, name, on_log, on_status)
        self.authtoken = authtoken

    def start(self):
        if self.running: return True
        if not self.is_installed(): return False
        
        if not self.authtoken.strip():
            if self.on_log: self.on_log(f"[{self.name}] Error: No se ha configurado el Authtoken de Ngrok en '⚙ Red IP'.")
            self.update_status("Error: Sin Authtoken", None)
            return False
            
        self.running = True
        self._safe_run(self._run_loop)
        return True

    def _run_loop(self):
        try:
            import re
            ip_pattern = re.compile(r'url=tcp://([a-zA-Z0-9.-]+:\d+)')
            
            cmd = [self.executable_path, "tcp", "25565", "--log=stdout", "--authtoken", self.authtoken.strip()]
            import os
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=creation_flags
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.running: break
                line = line.strip()
                if not line: continue
                
                if self.on_log: self.on_log(f"[{self.name}] {line}")
                
                lower_line = line.lower()
                if "authentication failed" in lower_line or "requires a valid authtoken" in lower_line or "requires a verified account" in lower_line:
                    self.update_status("Error: Token Ngrok Inválido", None)
                    break
                    
                match = ip_pattern.search(line)
                if match:
                    self.update_status("Activo", match.group(1))
                    
            if self.process: self.process.wait()
        except Exception as e:
            if self.on_log: self.on_log(f"[{self.name} Error] {e}")


class TunnelController:
    def __init__(self, data_dir, on_log=None, on_status_change=None):
        self.config_path = Path(data_dir) / "tunnel_settings.json"
        
        self.playit_path = "playit.exe" if os.name == 'nt' else "playit"
        self.ngrok_path = "ngrok.exe" if os.name == 'nt' else "ngrok"
        self.ngrok_token = ""
        self.fallback_timeout = 15 # seconds
        self.method_preference = "auto" # 'auto', 'playit', 'ngrok'
        
        self.on_log = on_log
        self.on_status_change = on_status_change
        
        self.active_tunnel = None
        self.is_running = False
        self._monitor_thread = None
        
        self.load_config()

    def load_config(self):
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                self.playit_path = data.get("playit_path", self.playit_path)
                self.ngrok_path = data.get("ngrok_path", self.ngrok_path)
                self.ngrok_token = data.get("ngrok_token", self.ngrok_token)
                self.fallback_timeout = data.get("fallback_timeout", 15)
                self.method_preference = data.get("method_preference", "auto")
            except: pass

    def save_config(self, playit, ngrok, token, timeout, pref):
        self.playit_path = playit if playit else self.playit_path
        self.ngrok_path = ngrok if ngrok else self.ngrok_path
        self.ngrok_token = token
        self.fallback_timeout = int(timeout)
        self.method_preference = pref
        self.config_path.write_text(json.dumps({
            "playit_path": self.playit_path,
            "ngrok_path": self.ngrok_path,
            "ngrok_token": self.ngrok_token,
            "fallback_timeout": self.fallback_timeout,
            "method_preference": self.method_preference
        }, indent=4))

    def set_callbacks(self, log_cb, status_cb):
        self.on_log = log_cb
        self.on_status_change = status_cb

    def update_ui(self, status, ip=None):
        if self.on_status_change:
            self.on_status_change(status, ip)

    def print_log(self, text):
        if self.on_log:
            self.on_log(text)
            
    def is_installed(self, method=None):
        if method == "Playit":
            return shutil.which(self.playit_path) is not None or Path(self.playit_path).exists()
        elif method == "Ngrok":
            return shutil.which(self.ngrok_path) is not None or Path(self.ngrok_path).exists()
        # Default check for active tunnel or both
        return (shutil.which(self.playit_path) is not None or Path(self.playit_path).exists()) or \
               (shutil.which(self.ngrok_path) is not None or Path(self.ngrok_path).exists())

    def _ensure_downloaded(self, method_name):
        import urllib.request
        import shutil
        bin_dir = Path(self.config_path).parent / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        
        if method_name == "Playit":
            import os
            if not self.is_installed("Playit"): # Fixed call
                self.print_log("[Sistema] Playit no detectado. Intentando descargar automáticamente...")
                p_path = bin_dir / ("playit.exe" if os.name == 'nt' else "playit")
                try:
                    req = urllib.request.Request("https://github.com/playit-cloud/playit-agent/releases/latest/download/playit-windows-x86_64.exe", headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as resp, open(p_path, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                    self.playit_path = str(p_path)
                    self.print_log("[Sistema] Playit descargado correctamente.")
                    self.save_config(self.playit_path, self.ngrok_path, self.ngrok_token, self.fallback_timeout, self.method_preference)
                except Exception as e:
                    self.print_log(f"[Sistema] Error descargando Playit: {e}")
                    
        elif method_name == "Ngrok":
            import os
            import zipfile
            if not self.is_installed("Ngrok"): # Fixed call
                self.print_log("[Sistema] Ngrok no detectado. Intentando descargar automáticamente...")
                n_zip = bin_dir / "ngrok.zip"
                n_path = bin_dir / ("ngrok.exe" if os.name == 'nt' else "ngrok")
                try:
                    req = urllib.request.Request("https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip", headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as resp, open(n_zip, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                    with zipfile.ZipFile(n_zip, 'r') as zip_ref:
                        zip_ref.extractall(bin_dir)
                    n_zip.unlink(missing_ok=True)
                    self.ngrok_path = str(n_path)
                    self.print_log("[Sistema] Ngrok descargado y extraído correctamente.")
                    self.save_config(self.playit_path, self.ngrok_path, self.ngrok_token, self.fallback_timeout, self.method_preference)
                except Exception as e:
                    self.print_log(f"[Sistema] Error descargando Ngrok: {e}")

    def _create_tunnel(self, tunnel_type):
        self._ensure_downloaded(tunnel_type)
        if tunnel_type == "Playit":
            tunnel = PlayitTunnel(self.playit_path, "Playit", self.print_log, self.update_ui)
        else:
            tunnel = NgrokTunnel(self.ngrok_path, "Ngrok", self.ngrok_token, self.print_log, self.update_ui)
        return tunnel

    def start(self):
        if self.is_running: return
        self.is_running = True
        self._monitor_thread = threading.Thread(target=self._connection_flow, daemon=True)
        self._monitor_thread.start()

    def _connection_flow(self):
        methods = []
        if self.method_preference == "auto":
            methods = ["Playit", "Ngrok"]
        elif self.method_preference == "playit":
            methods = ["Playit"]
        elif self.method_preference == "ngrok":
            methods = ["Ngrok"]

        for i, method_name in enumerate(methods):
            if not self.is_running: break
            
            self.print_log(f"[Sistema] Intentando conectar usando {method_name}...")
            prefix = "Conectando" if i == 0 else f"Fallback a {method_name}"
            self.update_ui(f"{prefix} ({method_name})", None)
            
            tunnel = self._create_tunnel(method_name)
            
            if not tunnel.is_installed():
                self.print_log(f"[Sistema] El ejecutable de {method_name} no se encontró incluso tras descarga.")
                continue

            self.active_tunnel = tunnel
            if not tunnel.start():
                continue # if it fails early (e.g. no authtoken)
            
            # Wait for connection or timeout
            start_time = time.time()
            connected = False
            while self.is_running and (time.time() - start_time) < self.fallback_timeout:
                if tunnel.public_ip:
                    connected = True
                    # Let the tunnel keep running
                    while self.is_running and tunnel.running:
                        time.sleep(1)
                    break
                
                if not tunnel.running:
                    # Tunnel crashed immediately
                    break
                time.sleep(1)

            if connected and not self.is_running:
                # Deliberate stop
                break
            
            # If we reach here, it either timed out or crashed without connecting
            if self.is_running and (i < len(methods) - 1):
                self.print_log(f"[Sistema] {method_name} falló o superó el tiempo límite. Cambiando herramienta...")
                if tunnel.running:
                    tunnel.stop()
                self.active_tunnel = None
                time.sleep(2) # brief pause before starting the fallback
        
        # If loop finishes and we are still running but no active tunnel
        if self.is_running and (not self.active_tunnel or not self.active_tunnel.public_ip):
            self.print_log("[Sistema] Todos los métodos de conexión fallaron.")
            self.update_ui("Error de Conexión", None)
            self.is_running = False
            if self.active_tunnel:
                self.active_tunnel.stop()

    def stop(self):
        self.is_running = False
        if self.active_tunnel:
            self.active_tunnel.stop()
            self.active_tunnel = None
        self.update_ui("Desconectado", None)
        self.print_log("[Sistema] Conexión pública detenida.")
