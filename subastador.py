import socket
import struct
import threading

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
SERVER_PORT = 5008

precio_actual = 20.0
mejor_postor = 'Ninguno'
lock = threading.Lock()

def escuchar_pujas():
    global precio_actual, mejor_postor

    # Socket para recibir pujas de los clientes (Unicast)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('', SERVER_PORT))

    # Socket para enviar la actualización por Multicast cuando ocurra un cambio
    sock_multicast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    ttl = struct.pack('b', 1) # Solo viaja localmente / red virtual
    sock_multicast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    print(f'Servidor listo. Escuchando pujas en el puerto {SERVER_PORT}...')

    while True:
        try:
            data, addr = server_socket.recvfrom(1024)
            mensaje = data.decode('utf-8')
            partes = mensaje.split(":")
            cliente_id = partes[0]
            ofertas = float(partes[1])

            with lock:
                if ofertas > precio_actual:
                    mejor_postor = cliente_id
                    precio_actual = ofertas
                    print(f"\n¡Nueva puja aceptada! Postor: {mejor_postor} | Cantidad: ${precio_actual}")

                    # ENVIAR MULTICAST INMEDIATAMENTE AL CAMBIAR EL ESTADO
                    mensaje_multicast = f"ESTADO_SUBASTA|Precio actual: ${precio_actual}, mejor postor: {mejor_postor}"
                    sock_multicast.sendto(mensaje_multicast.encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
                else:
                    print(f"\nPuja rechazada de {cliente_id} (${ofertas}): Es menor o igual al precio actual (${precio_actual}).")
        except Exception as e:
            print(f"[Error recibiendo puja]: {e}")

if __name__ == "__main__":
    # Ya no necesitamos el hilo de transmisión periódica, todo se maneja por eventos en el servidor
    escuchar_pujas()
