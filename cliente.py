import socket
import struct
import threading
import sys

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
SERVER_IP = input('n\Introduce la IP del servidor: ')
SERVER_PORT = 5008
CLIENTE_ID = input('n\Ingresa tu nombre: ')

def escuchar_multicast():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.SO_REUSEADDR)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', MULTICAST_PORT))

    group = socket.inet_aton(MULTICAST_GROUP)
    mreq = struct.pack('4s4s', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        data, _ = sock.recvfrom(1024)
        mensaje = data.decode('utf-8')
        print(f"n\Actualizacion: {mensaje}")
