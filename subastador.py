import socket #se usara UDP por velocidad
import struct
import threading #concurrencia
import time

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = '5007'
SERVER_PORT = '5008'

precio_actual = 20.0
mejor_postor = 'Ninguno'
lock = threading.Lock() #Lock asegura que un solo hilo modifique los datos a la vez

def escuchar_pujas():
    global precio_actual, mejor_postor
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('', SERVER_PORT))
    print(f'n\Escuchando pujas en el puerto {SERVER_PORT}')
    #Abre el puerto  mientras se escuchan las pujas no cierra
    while True:
        data, addr = server_socket.recvfrom(1024)
        mensaje = data.decode('utf-8')
        partes = mensaje.split(":")
        cliente_id = partes[0]
        ofertas = float(partes[1])
        #comprueba si la puja es mayor que el precio actual y si es mayor la asigna como nuevo precio
        with lock:
            if ofertas > precio_actual:
                mejor_postor = cliente_id
                precio_actual = ofertas
                print(f"n\Puja aceptada: '{mejor_postor}' pujo '{precio_actual}f'!")
            else:
                print('Puja rechazada :(')
def transmitir_estado():
    global precio_actual, mejor_postor

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    ttl = struct.pack('b', 1) #significa que el paquete solo viaja localmente
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    while True:
        with lock:
            mensaje = f"ESTADO_SUBASTA|Precio actual: {precio_actual}, mejor postor: {mejor_postor}"

        sock.sendto(mensaje.encode('utf-8'), (MULTICAST_GROUP ,MULTICAST_PORT))
        time.sleep(2) #se actualiza cada 2 segundos
