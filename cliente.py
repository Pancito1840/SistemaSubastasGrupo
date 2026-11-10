import socket
import struct
import threading
import sys

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
SERVER_IP = input('Introduce la IP del servidor: ')
SERVER_PORT = 5008
CLIENTE_ID = input('Ingresa tu nombre: ')

def escuchar_multicast():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MULTICAST_PORT))

    group = socket.inet_aton(MULTICAST_GROUP)
    # Corregido con bytes para evitar el struct.error en Python moderno
    mreq = struct.pack('4s4s', group, b'\x00\x00\x00\x00')
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        try:
            data, _ = sock.recvfrom(1024)
            mensaje = data.decode('utf-8')
            # Imprimimos de manera limpia y volvemos a mostrar el prompt del usuario
            print(f"\n[ACTUALIZACIÓN] {mensaje}")
            print(f"[{CLIENTE_ID}] Tu puja: ", end="", flush=True)
        except Exception as e:
            break

if __name__ == "__main__":
    hilo_escucha = threading.Thread(target=escuchar_multicast, daemon=True)
    hilo_escucha.start() # <--- ¡Agregados los paréntesis para que el hilo arranque!

    sock_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"\n--- Bienvenido a la Subasta, {CLIENTE_ID} ---")
    while True:
        try:
            oferta_str = input(f'[{CLIENTE_ID}] Tu puja: ')
            if not oferta_str:
                continue
            oferta = float(oferta_str)
            mensaje = f"{CLIENTE_ID}:{oferta}"
            sock_envio.sendto(mensaje.encode('utf-8'), (SERVER_IP, SERVER_PORT))
        except ValueError:
            print("Por favor, introduce un número válido.")
        except KeyboardInterrupt:
            print("\nSaliendo de la subasta...")
            sys.exit()
