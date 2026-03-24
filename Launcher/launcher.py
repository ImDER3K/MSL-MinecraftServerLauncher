import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext, ttk
import subprocess
import threading
import json
import os
import shutil
import re
import urllib.request
import urllib.error
from pathlib import Path
import customtkinter as ctk

# Import our new styles configuration
import styles

class MinecraftLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft Server Launcher")
        self.root.geometry("1100x750")

        # Apply styles
        self.styles = styles.apply_styles()
        self.root.configure(fg_color=self.styles["colors"]["bg"])

        # Persistent Storage
        if os.name == 'nt':
            appdata = os.getenv('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
            self.data_dir = Path(appdata) / "MinecraftServerLauncher"
        else:
            self.data_dir = Path.home() / ".minecraft_launcher"
            
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.servers_file = self.data_dir / "servers.json"
        
        # Load and potentially migrate local legacy servers.json
        self.servers = self.load_servers()

        self.server_processes = {}  # server_path: process
        self.server_consoles = {}   # server_path: console text widget
        self.console_tabs_index = {}
        self.active_players = {}    # server_path: set(player names)

        self.selected_server = None

        self.setup_ui()

    def load_servers(self):
        local_legacy_file = Path("servers.json")
        data = {}
        if local_legacy_file.exists():
            try:
                with open(local_legacy_file, 'r') as f:
                    legacy_data = json.load(f)
                    for name, path in legacy_data.items():
                        if isinstance(path, str):
                            data[path] = {"name": name, "version": "Vanilla"}
                        else:
                            data = legacy_data
                            break
                local_legacy_file.unlink()
                self._save_to_path(self.servers_file, data)
                return data
            except Exception as e:
                print(f"Error migrating local servers: {e}")

        if self.servers_file.exists():
            try:
                with open(self.servers_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
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

        list_title = ctk.CTkLabel(left_frame, text="Servers", font=self.styles["fonts"]["heading"], text_color=self.styles["colors"]["text"])
        list_title.pack(pady=(10, 5))

        self.server_list_frame = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
        self.server_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,5))

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

        self.btn_frame_start = ctk.CTkFrame(left_frame, fg_color="transparent")
        self.btn_frame_start.pack(fill=tk.X, pady=(0,5), padx=10)

        self.info_tabs = ctk.CTkTabview(left_frame, height=180, 
                                        fg_color=self.styles["colors"]["bg"],
                                        segmented_button_fg_color=self.styles["colors"]["bg"],
                                        segmented_button_selected_color=self.styles["colors"]["primary"],
                                        segmented_button_unselected_color=self.styles["colors"]["bg"])
        self.info_tabs.pack(fill=tk.X, expand=False, padx=10, pady=(0, 10))
        self.info_tabs.add("Players")
        self.info_tabs.add("Plugins")
        
        self.players_text = scrolledtext.ScrolledText(self.info_tabs.tab("Players"), 
                                                      bg=self.styles["colors"]["bg"], fg=self.styles["colors"]["text"], 
                                                      font=self.styles["fonts"]["body"], borderwidth=0, highlightthickness=0, state=tk.DISABLED)
        self.players_text.pack(fill=tk.BOTH, expand=True)

        self.plugins_text = scrolledtext.ScrolledText(self.info_tabs.tab("Plugins"), 
                                                      bg=self.styles["colors"]["bg"], fg=self.styles["colors"]["text"], 
                                                      font=self.styles["fonts"]["body"], borderwidth=0, highlightthickness=0, state=tk.DISABLED)
        self.plugins_text.pack(fill=tk.BOTH, expand=True)

        right_frame = ctk.CTkFrame(main_frame, fg_color=self.styles["colors"]["fg"], corner_radius=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10,0))

        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("TNotebook", background=self.styles["colors"]["fg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=self.styles["colors"]["bg"], foreground=self.styles["colors"]["text"], padding=[10, 2], font=self.styles["fonts"]["body"])
        style.map("TNotebook.Tab", background=[("selected", self.styles["colors"]["primary"])])
        
        self.console_notebook = ttk.Notebook(right_frame)
        self.console_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

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
                     command=self.send_global_command).pack(side=tk.RIGHT, padx=(5,0))

        self.refresh_servers()

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

    def create_server(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Install New Server")
        dialog.geometry("450x450")
        dialog.transient(self.root)
        dialog.grab_set()

        name_var = tk.StringVar(value="My New Server")
        loc_var = tk.StringVar()
        type_var = tk.StringVar(value="Paper")
        ver_var = tk.StringVar(value="1.20.4")
        ram_var = tk.StringVar(value="4G")

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
        ctk.CTkOptionMenu(row_frame1, variable=ver_var, values=["1.21.1", "1.20.4", "1.19.4", "1.18.2", "1.16.5", "1.12.2"], width=150).grid(row=1, column=1, sticky="w")

        row_frame2 = ctk.CTkFrame(wrapper, fg_color="transparent")
        row_frame2.pack(fill=tk.X, pady=(0, 15))
        
        ctk.CTkLabel(row_frame2, text="RAM (e.g., 4G):").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(row_frame2, textvariable=ram_var, width=150).grid(row=1, column=0, sticky="w")

        status_lbl = ctk.CTkLabel(wrapper, text="", text_color=self.styles["colors"]["text_muted"])
        status_lbl.pack(pady=5)
        
        create_btn = ctk.CTkButton(wrapper, text="Download & Create", fg_color=self.styles["colors"]["success"], hover_color="#2b9348")
        create_btn.pack(pady=10, fill=tk.X)

        def download_and_setup(name, loc, server_type, ver, ram, dialog_window):
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
                    raise Exception("Forge requires the manual Forge Installer. Download the installer visually from MinecraftForge, use the 'Add Existing' button upon install!")
                    
            except Exception as e:
                messagebox.showerror("Download Error", str(e))
                shutil.rmtree(target_folder, ignore_errors=True)
                create_btn.configure(state="normal", text="Download & Create")
                status_lbl.configure(text="Download failed.")
                return

            status_lbl.configure(text="Writing Configuration...")
            (target_folder / "eula.txt").write_text("eula=true\n")
            (target_folder / "start.bat").write_text(f"java -Xmx{ram} -Xms{ram} -jar server.jar nogui\n")

            self.root.after(0, finalize_creation, target_folder, name, ver, dialog_window)

        def finalize_creation(target_folder, name, ver, dialog_window):
            path_key = str(target_folder.absolute())
            self.servers[path_key] = {"name": name, "version": ver}
            self.save_servers()
            self.refresh_servers()
            self.on_server_select(path_key)
            dialog_window.destroy()
            messagebox.showinfo("Success", f"Server '{name}' automatically installed and created successfully!")

        def submit():
            name = name_var.get().strip()
            loc = loc_var.get().strip()
            server_type = type_var.get()
            ver = ver_var.get().strip()
            ram = ram_var.get().strip()

            if not all([name, loc, ver, ram]):
                messagebox.showerror("Error", "Please fill all fields, including the install location.")
                return
                
            create_btn.configure(state="disabled", text="Working...")
            threading.Thread(target=download_and_setup, args=(name, loc, server_type, ver, ram, dialog), daemon=True).start()

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
        self.servers[path_key] = {"name": folder_name, "version": "Unknown"}
        self.save_servers()
        self.refresh_servers()

    def edit_server(self):
        if not self.selected_server:
            messagebox.showinfo("Select Server", "Please select a server to edit.")
            return

        data = self.servers[self.selected_server]
        
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Edit Server")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Server Name:").pack(pady=(10, 0))
        name_entry = ctk.CTkEntry(dialog, width=200)
        name_entry.insert(0, data.get("name", ""))
        name_entry.pack(pady=5)

        ctk.CTkLabel(dialog, text="Server Version:").pack(pady=(10, 0))
        ver_entry = ctk.CTkEntry(dialog, width=200)
        ver_entry.insert(0, data.get("version", ""))
        ver_entry.pack(pady=5)

        def save_changes():
            self.servers[self.selected_server]["name"] = name_entry.get()
            self.servers[self.selected_server]["version"] = ver_entry.get()
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
        
        # Hard Deletion Warning
        confirm = messagebox.askyesno("Delete Server", 
                                      f"Are you sure you want to completely delete '{name}' and ALL its files from your PC?\n\nThis action cannot be cleanly reversed.",
                                      icon='warning')
        if not confirm:
            return
            
        # Hard Deletion Execution
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
            
        self.update_plugins_list(path_key)
        self.update_players_list(path_key)

    def update_plugins_list(self, path_key):
        plugins_dir = Path(path_key) / "plugins"
        plugins = []
        if plugins_dir.exists() and plugins_dir.is_dir():
            for jar in plugins_dir.glob("*.jar"):
                plugins.append(f"• {jar.name}")
        
        if plugins:
            txt = f"Found {len(plugins)} plugins:\n\n" + "\n".join(plugins)
        else:
            txt = "No plugins found or Vanilla server."
        self._update_text_widget(self.plugins_text, txt)

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
        start_file = None
        bat_path = Path(path_key) / "start.bat"
        if bat_path.exists():
            start_file = str(bat_path)
        else:
            jar_files = list(Path(path_key).glob("*.jar"))
            if jar_files:
                start_cmd = f'java -Xmx4G -Xms4G -jar {jar_files[0].name} nogui'
                bat_path.write_text(start_cmd)
                start_file = str(bat_path)

        if not start_file:
            messagebox.showerror("Error", "No start.bat or jar found")
            return

        try:
            process = subprocess.Popen(
                start_file,
                cwd=path_key,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
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
        if path_key in self.server_processes:
            process = self.server_processes[path_key]
            process.stdin.write("stop\n")
            process.stdin.flush()
            process.wait(timeout=30)
            del self.server_processes[path_key]
            self.active_players[path_key] = set()
            self.refresh_servers()
            self.on_server_select(path_key)

    def parse_console_for_players(self, path_key, line):
        join_match = re.search(r'([a-zA-Z0-9_]{3,16})\s+joined the game', line)
        if join_match:
            player = join_match.group(1)
            self.active_players[path_key].add(player)
            if self.selected_server == path_key:
                self.root.after(0, self.update_players_list, path_key)
                
        leave_match = re.search(r'([a-zA-Z0-9_]{3,16})\s+left the game', line)
        if leave_match:
            player = leave_match.group(1)
            if player in self.active_players[path_key]:
                self.active_players[path_key].remove(player)
            if self.selected_server == path_key:
                self.root.after(0, self.update_players_list, path_key)

    def read_console(self, path_key, stdout):
        console_tab = self.get_or_create_console_tab(path_key)
        while True:
            line = stdout.readline()
            if not line:
                break
            
            self.parse_console_for_players(path_key, line)
            self.root.after(0, self._insert_console_line, console_tab, line)
            
    def _insert_console_line(self, console_tab, line):
        console_tab.insert(tk.END, line)
        console_tab.see(tk.END)

    def get_or_create_console_tab(self, path_key):
        if path_key not in self.server_consoles:
            console_frame = ctk.CTkFrame(self.console_notebook, fg_color=self.styles["colors"]["bg"])
            name = self.servers.get(path_key, {}).get("name", "Unknown")
            self.console_notebook.add(console_frame, text=name)
            self.console_tabs_index[path_key] = self.console_notebook.index(console_frame)
            console_text = scrolledtext.ScrolledText(console_frame, height=15, 
                                                     bg=self.styles["colors"]["bg"], 
                                                     fg=self.styles["colors"]["text"],
                                                     font=self.styles["fonts"]["console"],
                                                     insertbackground=self.styles["colors"]["text"],
                                                     borderwidth=0, highlightthickness=0)
            console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
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

if __name__ == "__main__":
    root = ctk.CTk()
    app = MinecraftLauncher(root)
    root.mainloop()
