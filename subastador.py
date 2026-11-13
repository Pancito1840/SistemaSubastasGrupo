import math
import socket
import time

SERVER_PORT = 5008
# Escucha en todas las interfaces, incluida la interfaz de Hamachi.
BIND_IP = '0.0.0.0'
CLIENT_TIMEOUT = 30
precio_actual = 20.0
mejor_postor = 'Ninguno'


def estado():
    return f'ESTADO_SUBASTA|Precio actual: ${precio_actual:.2f}, mejor postor: {mejor_postor}'


def main():
    global precio_actual, mejor_postor
    clientes = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as servidor:
        servidor.bind((BIND_IP, SERVER_PORT))
        print(f'Servidor UDP escuchando en el puerto {SERVER_PORT} (todas las interfaces).')
        print(estado())

        def enviar(mensaje, destino):
            try:
                servidor.sendto(mensaje.encode('utf-8'), destino)
            except OSError as exc:
                print(f'No se pudo enviar una actualización: {exc}')

        while True:
            data, addr = servidor.recvfrom(2048)
            try:
                mensaje = data.decode('utf-8').strip()
                if mensaje == 'SALIR':
                    clientes.pop(addr, None)
                    continue
                if mensaje == 'ESTADO':
                    clientes[addr] = time.monotonic()
                    enviar(estado(), addr)
                    continue
                nombre, cantidad = mensaje.split(':', 1)
                nombre = nombre.strip()
                if not nombre or len(nombre) > 40 or any(c in nombre for c in '|:\n\r'):
                    raise ValueError('Nombre de postor inválido')
                oferta = float(cantidad)
                if not math.isfinite(oferta) or oferta <= 0:
                    raise ValueError('La oferta debe ser un número positivo y finito')
                clientes[addr] = time.monotonic()
                if oferta <= precio_actual:
                    respuesta = f'RECHAZADA|Tu oferta ${oferta:.2f} debe superar ${precio_actual:.2f}'
                    enviar(respuesta, addr)
                    enviar(estado(), addr)
                    print(f'Oferta rechazada: {nombre} (${oferta:.2f})')
                    continue
                precio_actual, mejor_postor = oferta, nombre
                respuesta = f'ACEPTADA|Tu oferta de ${oferta:.2f} fue aceptada'
                enviar(respuesta, addr)
                print(f'Nueva oferta: {nombre} (${oferta:.2f})')
                print(estado())
                # Un fallo al enviar a un cliente no impide actualizar a los demás.
                ahora = time.monotonic()
                for cliente, ultima_consulta in list(clientes.items()):
                    if ahora - ultima_consulta > CLIENT_TIMEOUT:
                        clientes.pop(cliente, None)
                    else:
                        enviar(estado(), cliente)
            except (UnicodeError, ValueError) as exc:
                enviar(f'ERROR|{exc}', addr)
                print(f'Mensaje inválido desde {addr}: {exc}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido.')
    except OSError as exc:
        print(f'No se pudo iniciar el servidor: {exc}')
        print(f'Comprueba que el puerto UDP {SERVER_PORT} esté disponible.')
