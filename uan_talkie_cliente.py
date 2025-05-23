import socket
import pyaudio
import threading
import tkinter as tk
from tkinter import messagebox
import os
import wave
from datetime import datetime
import struct

# Configuración de audio y red
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
PORT = 50007
BUFFER_SIZE = 4096

# Función para obtener la IP local de la interfaz activa
def get_local_ip():
    try:
        # Conectamos a un host público para obtener la IP local asignada (sin enviar datos)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# Función para calcular la dirección de broadcast dado IP y máscara
def ip_broadcast(ip, netmask):
    ip_packed = struct.unpack('>I', socket.inet_aton(ip))[0]
    mask_packed = struct.unpack('>I', socket.inet_aton(netmask))[0]
    broadcast_packed = ip_packed | (~mask_packed & 0xFFFFFFFF)
    broadcast_ip = socket.inet_ntoa(struct.pack('>I', broadcast_packed))
    return broadcast_ip

# Función para obtener máscara de red de la interfaz usada para la IP local
def get_netmask(local_ip):
    # Este método es más simple y funciona en Windows y Linux para interfaces estándar
    # Usaremos getaddrinfo para la IP local y sacamos máscara de red con socket.if_nameindex y si lo permite
    # Pero para simplificar, usaremos máscara común de clase C: 255.255.255.0
    # Puedes mejorar esta parte usando librerías como netifaces si quieres más precisión
    return "255.255.255.0"

# Obtener IP local y broadcast automático
local_ip = get_local_ip()
netmask = get_netmask(local_ip)
TARGET_IP = ip_broadcast(local_ip, netmask)
print(f"IP local detectada: {local_ip}")
print(f"Máscara de red asumida: {netmask}")
print(f"Dirección broadcast calculada: {TARGET_IP}")

# Inicializar PyAudio y sockets
audio = pyaudio.PyAudio()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(('', PORT))

# Streams
stream_input = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
stream_output = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

# Carpeta de almacenamiento
DIRECTORIO_MENSAJES = "mensajes_recibidos"
os.makedirs(DIRECTORIO_MENSAJES, exist_ok=True)

# Estado
transmitting = False
current_record = []
running = True

# Guardar mensaje como archivo WAV
def guardar_mensaje(frames):
    nombre = f"mensaje_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    ruta = os.path.join(DIRECTORIO_MENSAJES, nombre)
    with wave.open(ruta, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    return nombre

# Transmisión de voz
def transmit_audio():
    global transmitting
    while transmitting and running:
        try:
            data = stream_input.read(CHUNK)
            sock.sendto(data, (TARGET_IP, PORT))
        except Exception as e:
            print(f"Error al transmitir: {e}")
            break

# Recepción de voz y almacenamiento
def receive_audio():
    global current_record
    while running:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            stream_output.write(data)
            current_record.append(data)
        except Exception as e:
            if running:
                print(f"Error al recibir audio: {e}")
            break

# Finalizar grabación y guardar
def guardar_si_hay_audio():
    global current_record
    if current_record:
        nombre = guardar_mensaje(current_record)
        mensajes_listbox.insert(tk.END, nombre)
        current_record = []

# Alternar transmisión
def toggle_transmit(event):
    global transmitting
    if not transmitting:
        transmitting = True
        threading.Thread(target=transmit_audio, daemon=True).start()
        button.config(text="Transmitiendo... (suelta para parar)", bg="red")
    else:
        transmitting = False
        button.config(text="Presiona para Hablar", bg="green")
        guardar_si_hay_audio()

# Reproducir mensaje seleccionado
def reproducir_mensaje():
    seleccion = mensajes_listbox.curselection()
    if not seleccion:
        messagebox.showinfo("Info", "Selecciona un mensaje para reproducir.")
        return

    archivo = mensajes_listbox.get(seleccion[0])
    ruta = os.path.join(DIRECTORIO_MENSAJES, archivo)

    try:
        with wave.open(ruta, 'rb') as wf:
            stream = audio.open(format=audio.get_format_from_width(wf.getsampwidth()),
                                channels=wf.getnchannels(),
                                rate=wf.getframerate(),
                                output=True)
            data = wf.readframes(CHUNK)
            while data:
                stream.write(data)
                data = wf.readframes(CHUNK)
            stream.stop_stream()
            stream.close()
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo reproducir el mensaje: {e}")

# Al cerrar la ventana
def on_closing():
    global running, transmitting
    running = False
    transmitting = False
    try:
        sock.close()  # cerrar socket para desbloquear recvfrom
    except:
        pass
    stream_input.stop_stream()
    stream_input.close()
    stream_output.stop_stream()
    stream_output.close()
    audio.terminate()
    root.destroy()

# GUI
root = tk.Tk()
root.title("Walkie LAN con mensajes guardados")

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

button = tk.Button(frame, text="Presiona para Hablar", font=("Arial", 16), width=30, height=2, bg="green")
button.bind('<ButtonPress>', toggle_transmit)
button.bind('<ButtonRelease>', toggle_transmit)
button.pack(pady=10)

mensajes_listbox = tk.Listbox(frame, width=50, height=10)
mensajes_listbox.pack(pady=5)

btn_reproducir = tk.Button(frame, text="Reproducir Mensaje Seleccionado", command=reproducir_mensaje)
btn_reproducir.pack(pady=5)

# Cargar mensajes existentes
for archivo in sorted(os.listdir(DIRECTORIO_MENSAJES)):
    if archivo.endswith(".wav"):
        mensajes_listbox.insert(tk.END, archivo)

# Hilo de recepción
threading.Thread(target=receive_audio, daemon=True).start()

# Evento de cerrar ventana
root.protocol("WM_DELETE_WINDOW", on_closing)

# Ejecutar GUI
root.mainloop()
