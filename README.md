# Minecraft Server Launcher

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0-blue">
  <img src="https://img.shields.io/badge/python-3.10+-green">
  <img src="https://img.shields.io/badge/ui-CustomTkinter-black">
  <img src="https://img.shields.io/badge/status-active-success">
</p>

Un gestor de servidores de Minecraft orientado a simplificar la creación, administración y monitoreo desde una sola interfaz.  

A Minecraft server manager designed to simplify creation, administration, and monitoring from a single interface.

---

## Tabla de contenido / Table of Contents

- [Características / Features](#características--features)  
- [Instalación / Installation](#instalación--installation)  
- [Uso / Usage](#uso--usage)  
- [Estructura / Structure](#estructura-del-proyecto--project-structure)  
- [Roadmap](#roadmap)  
- [Contribución / Contributing](#contribución--contributing)  

---

## Características / Features

### Creación automática de servidores / Automatic server creation

Descarga versiones directamente desde APIs oficiales de PaperMC y Mojang (Vanilla), evitando configuraciones manuales.  

Downloads server versions directly from official PaperMC and Mojang (Vanilla) APIs, removing manual setup.

Incluye / Includes:

- Aceptación automática del EULA / Automatic EULA acceptance  
- Generación de script de arranque / Startup script generation  
- Configuración de memoria RAM / RAM allocation setup  

---

### Persistencia de datos / Data persistence

Los servidores se almacenan en AppData, manteniendo la información aunque el programa cambie de ubicación.  

Servers are stored in AppData, preserving data even if the application is moved.

- Edición de nombre y versión sin afectar rutas internas  
- Independent metadata editing without breaking paths  

---

### Monitoreo en tiempo real / Real-time monitoring

El sistema analiza la actividad del servidor desde la consola.  

The system analyzes server activity directly from console output.

- Detección de jugadores activos / Active player tracking  
- Identificación automática de plugins / Automatic plugin detection  

---

### Interfaz y control / Interface and control

Interfaz basada en CustomTkinter enfocada en claridad.  

CustomTkinter-based interface focused on usability.

- Selección mediante tarjetas / Card-based selection  
- Consolas separadas / Per-server consoles  
- Envío de comandos / Command execution  

---

### Gestión de almacenamiento / Storage management

Eliminación completa de servidores desde la aplicación.  

Full server deletion directly from the app.

- Borrado total de archivos / Full file removal  
- Confirmación previa / Confirmation prompt  

---

## Instalación / Installation

git clone https://github.com/tu-usuario/minecraft-server-launcher.git
cd minecraft-server-launcher
pip install -r requirements.txt
python main.py


Uso / Usage
Español
Crear un nuevo servidor
Seleccionar versión y RAM
Iniciar el servidor
Administrar desde la consola

English
Create a new server
Select version and RAM
Start the server
Manage it from the console

---

Estructura del proyecto / Project Structure
minecraft-server-launcher/
│
├── main.py
├── styles.py
├── server_manager/
├── ui/
├── utils/
└── assets/

--- 
Roadmap

Integración con túneles de red usando Playit (sin necesidad de abrir puertos)

Network tunneling integration with Playit (no port forwarding required)

Sistema de backups automáticos

Automatic backup system

Soporte para múltiples perfiles

Multi-profile support

Mejoras en monitoreo

Monitoring improvements

---

Contribución / Contributing

Español
Haz un fork del proyecto
Crea una rama (feature/nueva-funcion)
Realiza cambios
Envía un pull request

English
Fork the repository
Create a branch (feature/new-feature)
Make your changes
Submit a pull request
Licencia / License

---

Este proyecto está bajo licencia MIT.

This project is licensed under the MIT License.
