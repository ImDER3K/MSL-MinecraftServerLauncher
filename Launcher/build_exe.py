import os
import sys
import subprocess
import shutil
import glob

def main():
    print("Instalando/Actualizando PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])
    
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)
    
    python_version = f"{sys.version_info.major}{sys.version_info.minor}"
    python_dir = os.path.dirname(sys.executable)
    
    # Buscar python3XX.dll en distintas ubicaciones posibles
    dll_name = f"python{python_version}.dll"
    dll_paths_to_check = [
        os.path.join(python_dir, dll_name),
        os.path.join(python_dir, "..", dll_name),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), dll_name),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "System32", dll_name),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "SysWOW64", dll_name),
    ]
    
    # Copiar la DLL al directorio actual si se encuentra (fix para MS Store Python)
    dll_found = None
    for dll_path in dll_paths_to_check:
        if os.path.exists(dll_path):
            dll_found = dll_path
            break
    
    extra_args = []
    if dll_found:
        print(f"  [OK] DLL de Python encontrada: {dll_found}")
        shutil.copy2(dll_found, ".")
        extra_args += [f"--add-binary={dll_name};."]
    else:
        # Último intento: buscar con glob en todo el sistema (puede tardar)
        print(f"  [WARN] DLL '{dll_name}' no encontrada en rutas estándar.")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--icon=icon.ico",
        "--collect-all", "customtkinter",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.scrolledtext",
        f"--add-data={ctk_path};customtkinter/",
        "--add-data=icon.ico;.",
    ] + extra_args + ["launcher.py"]
    
    print("Ejecutando PyInstaller para crear el ejecutable...")
    try:
        subprocess.check_call(cmd)
        
        # El onefile siempre pone el exe directamente en dist/
        dist_exe = os.path.join("dist", "launcher.exe")
        
        if os.path.exists(dist_exe):
            out_exe = "Minecraft Server Launcher.exe"
            if os.path.exists(out_exe):
                os.remove(out_exe)
            shutil.copy(dist_exe, out_exe)
            size_mb = os.path.getsize(out_exe) / (1024 * 1024)
            print(f"\n\n¡Compilación exitosa!")
            print(f"  Archivo: {out_exe}")
            print(f"  Tamaño:  {size_mb:.1f} MB")
            print("\nPuedes distribuir ese único .exe, no necesita instalación adicional.")
            
            # Limpiar DLL temporal si la copiamos
            if dll_found and os.path.exists(dll_name):
                os.remove(dll_name)
        else:
            print("No se pudo encontrar el ejecutable en 'dist'. Revisa los logs arriba.")

    except subprocess.CalledProcessError as e:
        print(f"Error durante empaquetado: {e}")
        # Limpiar DLL temporal
        if dll_found and os.path.exists(dll_name):
            os.remove(dll_name)

if __name__ == "__main__":
    main()
