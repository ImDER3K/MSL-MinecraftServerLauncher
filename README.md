Minecraft Server Launcher
<p align="center"> <img src="https://img.shields.io/badge/version-1.0-blue"> <img src="https://img.shields.io/badge/python-3.10+-green"> <img src="https://img.shields.io/badge/ui-CustomTkinter-black"> <img src="https://img.shields.io/badge/status-active-success"> </p>

Un gestor de servidores de Minecraft orientado a simplificar la creación, administración y monitoreo desde una sola interfaz. Diseñado para eliminar procesos manuales y hacer más directo el manejo de servidores locales.

Tabla de contenido
Características
Instalación
Uso
Estructura
Roadmap
Contribución
Características
Creación automática de servidores

Descarga versiones directamente desde APIs oficiales de PaperMC y Mojang (Vanilla), evitando configuraciones manuales.

Incluye:

Aceptación automática del EULA
Generación de script de arranque
Configuración de memoria RAM
Persistencia de datos

Los servidores se almacenan en AppData, permitiendo mantener la información incluso si el programa cambia de ubicación.

Edición de nombre y versión sin afectar rutas internas
Gestión independiente por servidor
Monitoreo en tiempo real

El sistema analiza la actividad del servidor directamente desde la consola.

Detección de jugadores activos
Identificación automática de plugins instalados
Interfaz y control

Interfaz basada en CustomTkinter enfocada en claridad y control.

Selección de servidores mediante tarjetas
Consolas separadas por servidor
Envío de comandos en tiempo real
Gestión de almacenamiento

Eliminación completa de servidores desde la aplicación.

Borrado total de archivos
Confirmación previa para evitar errores
Instalación
git clone https://github.com/tu-usuario/minecraft-server-launcher.git
cd minecraft-server-launcher
pip install -r requirements.txt
python main.py
Uso
Crear un nuevo servidor desde la interfaz
Seleccionar versión y memoria RAM
Iniciar el servidor
Administrar desde la consola integrada
Estructura del proyecto
minecraft-server-launcher/
│
├── main.py
├── styles.py
├── server_manager/
├── ui/
├── utils/
└── assets/
Roadmap
Integración con túneles de red usando Playit (sin necesidad de abrir puertos)
Sistema de backups automáticos
Soporte para múltiples perfiles de configuración
Mejoras en monitoreo y métricas del servidor
Contribución

Si quieres aportar:

Haz un fork del proyecto
Crea una rama (feature/nueva-funcion)
Realiza tus cambios
Envía un pull request
Licencia

Este proyecto está bajo licencia MIT.
