import math
import socket
import threading

SERVER_PORT = 5008


def escuchar_respuestas(sock, nombre):
    ultimo_estado = None
    while True:
        try:
            data, _ = sock.recvfrom(2048)
            mensaje = data.decode("utf-8", errors="replace")
            if mensaje.startswith("ESTADO_SUBASTA|"):
                if mensaje == ultimo_estado:
                    continue
                ultimo_estado = mensaje
            print(f'\n[SERVIDOR] {mensaje}')
            print(f'[{nombre}] Tu puja: ', end='', flush=True)
        except OSError:
            return


def consultar_estado(sock, detener):
    # UDP puede perder paquetes: consultar permite recuperar el estado actual.
    while not detener.wait(2):
        try:
            sock.send(b'ESTADO')
        except OSError:
            return


def main():
    server_ip = input('IP del servidor (local o Hamachi; Enter = 127.0.0.1): ').strip() or '127.0.0.1'
    nombre = input('Nombre del postor: ').strip()
    if not nombre or len(nombre) > 40 or any(c in nombre for c in ':|\r\n'):
        print('Nombre inválido (máx. 40 caracteres, sin : ni |).')
        return
    try:
        socket.inet_aton(server_ip)
    except OSError:
        print('Debes indicar una dirección IPv4 válida.')
        return
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((server_ip, SERVER_PORT))
        detener = threading.Event()
        threading.Thread(target=escuchar_respuestas, args=(sock, nombre), daemon=True).start()
        sock.send(b'ESTADO')
        threading.Thread(target=consultar_estado, args=(sock, detener), daemon=True).start()
        print('Solicitud de estado enviada. Escribe salir para finalizar.')
        try:
            while True:
                texto = input(f'[{nombre}] Tu puja: ').strip()
                if texto.lower() == 'salir':
                    break
                try:
                    oferta = float(texto)
                    if not math.isfinite(oferta) or oferta <= 0:
                        raise ValueError
                except ValueError:
                    print('Introduce un importe positivo válido.')
                    continue
                sock.send(f'{nombre}:{oferta}'.encode('utf-8'))
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            detener.set()
            try:
                sock.send(b'SALIR')
            except OSError:
                pass
    print('\nCliente finalizado.')


if __name__ == '__main__':
    try:
        main()
    except OSError as exc:
        print(f'Error de conexión: {exc}')
