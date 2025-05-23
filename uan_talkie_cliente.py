import socket
import pyaudio
import threading
import tkinter as tk
from tkinter import messagebox
import os
import wave
from datetime import datetime
import struct
import time

# Configuración de audio y red
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
PORT = 50007
BUFFER_SIZE = 4096

# Obtener IP local y broadcast
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def ip_broadcast(ip, netmask):
    ip_packed = struct.unpack('>I', socket.inet_aton(ip))[0]
    mask_packed = struct.unpack('>I', socket.inet_aton(netmask))[0]
    broadcast_packed = ip_packed | (~mask_packed & 0xFFFFFFFF)
    return socket.inet_ntoa(struct.pack('>I', broadcast_packed))

def get_netmask(_):
    return "255.255.255.0"

local_ip = get_local_ip()
netmask = get_netmask(local_ip)
TARGET_IP = ip_broadcast(local_ip, netmask)

print(f"IP local: {local_ip}")
print(f"Broadcast: {TARGET_IP}")

# Inicialización de audio y red
audio = pyaudio.PyAudio()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(('', PORT))

stream_input = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
stream_output = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

# Directorio de mensajes
DIRECTORIO_MENSAJES = "mensajes_recibidos"
os.makedirs(DIRECTORIO_MENSAJES, exist_ok=True)

# Variables globales
transmitting = False
running = True
current_record = []

# Guardar mensaje en .wav
def guardar_mensaje(frames):
    nombre = f"mensaje_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    ruta = os.path.join(DIRECTORIO_MENSAJES, nombre)
    with wave.open(ruta, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    return nombre

def guardar_si_hay_audio():
    global current_record
    if current_record:
        nombre = guardar_mensaje(current_record)
        mensajes_listbox.insert(tk.END, nombre)
        current_record = []

# Transmitir voz
def transmit_audio():
    global transmitting
    while transmitting and running:
        try:
            data = stream_input.read(CHUNK, exception_on_overflow=False)
            sock.sendto(data, (TARGET_IP, PORT))
        except Exception as e:
            print(f"Error transmitiendo: {e}")
            break

# Recibir voz (y guardar)
def receive_audio():
    global current_record
    while running:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            if addr[0] == local_ip:
                continue  # Ignora el audio propio

            stream_output.write(data)
            current_record.append(data)
        except Exception as e:
            if running:
                print(f"Error al recibir: {e}")
            break

# Guardar periódicamente lo recibido
def guardar_periodicamente():
    while running:
        time.sleep(5)
        guardar_si_hay_audio()

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
        messagebox.showerror("Error", f"No se pudo reproducir: {e}")

# Al cerrar ventana
def on_closing():
    global running, transmitting
    running = False
    transmitting = False
    try:
        sock.close()
    except:
        pass
    stream_input.stop_stream()
    stream_input.close()
    stream_output.stop_stream()
    stream_output.close()
    audio.terminate()
    root.destroy()

# Interfaz
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

# Cargar mensajes previos
for archivo in sorted(os.listdir(DIRECTORIO_MENSAJES)):
    if archivo.endswith(".wav"):
        mensajes_listbox.insert(tk.END, archivo)

# Hilos en segundo plano
threading.Thread(target=receive_audio, daemon=True).start()
threading.Thread(target=guardar_periodicamente, daemon=True).start()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
