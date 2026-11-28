import socket
import json
import math
import uuid
import threading
import queue

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
SERVER_PORT = 5008


def interfaz_hacia(ip):
    # UDP connect consulta la ruta sin enviar paquetes.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as ruta:
        ruta.connect((ip, SERVER_PORT))
        return ruta.getsockname()[0]


def main():
    precio, postor, version = 20.0, 'Ninguno', 0
    sesion = uuid.uuid4().hex
    registrados = {}
    pendientes = queue.Queue(maxsize=1024)
    detener = threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receptor, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as emisor:
        receptor.bind(('', SERVER_PORT))
        receptor.settimeout(0.5)
        emisor.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        emisor.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        def publicar(destinos, destinatario=None):
            mensaje = json.dumps(dict(tipo='ESTADO_SUBASTA', sesion=sesion, version=version, precio=precio, postor=postor, destinatario=destinatario)).encode()
            enviar_multicast(mensaje, destinos)
        def responder_puja(cid, oferta, aceptada, interfaz):
            mensaje = json.dumps(dict(tipo='RESULTADO_PUJA', destinatario=cid, oferta=oferta, aceptada=aceptada, precio=precio)).encode()
            enviar_multicast(mensaje, {interfaz})
        def enviar_multicast(mensaje, destinos):
            for ip in sorted(destinos):
                try:
                    emisor.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                    emisor.sendto(mensaje, (MULTICAST_GROUP, MULTICAST_PORT))
                except OSError as e:
                    print(f'Error multicast en {ip}: {e}', flush=True)
        def escuchar():
            while not detener.is_set():
                try:
                    datos, addr = receptor.recvfrom(4096)
                    try:
                        pendientes.put_nowait((datos, addr))
                    except queue.Full:
                        print('Cola llena: datagrama descartado.', flush=True)
                except socket.timeout:
                    continue
                except OSError as e:
                    if not detener.is_set():
                        print(f'Error de recepción: {e}', flush=True)
                    detener.set()
        print(f'Subastador iniciado | Escucha unicast UDP: 0.0.0.0:{SERVER_PORT}', flush=True)
        print(f'Grupo multicast: {MULTICAST_GROUP}:{MULTICAST_PORT} (envío)', flush=True)
        print(f'Subasta abierta | Mejor oferta: ${precio:.2f} | Mejor postor: {postor}', flush=True)
        hilo = threading.Thread(target=escuchar, name='Recepción UDP')
        hilo.start()
        try:
            # Solo este hilo modifica el estado y usa el socket multicast.
            while not detener.is_set():
                try:
                    datos, addr = pendientes.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    m = json.loads(datos.decode())
                    if not isinstance(m, dict):
                        continue
                    tipo, cid, nombre = m['tipo'], m['id'], m['nombre']
                    if not isinstance(cid, str) or len(cid) != 32 or not isinstance(nombre, str) or not nombre.strip() or len(nombre)>80 or not nombre.isprintable():
                        continue
                    if tipo == 'REGISTRO':
                        interfaz = interfaz_hacia(addr[0])
                        registro = (nombre, addr, interfaz)
                        if cid in registrados and registrados[cid] != registro:
                            continue
                        if cid not in registrados:
                            print(f'Postor conectado: {nombre} | IP: {addr[0]}', flush=True)
                        registrados[cid] = registro
                        publicar({interfaz}, cid)
                    elif tipo == 'PUJA' and cid in registrados and registrados[cid][:2] == (nombre, addr):
                        oferta = float(m['oferta'])
                        if not math.isfinite(oferta) or oferta <= 0:
                            continue
                        aceptada = oferta > precio
                        if aceptada:
                            precio, postor = oferta, nombre
                            version += 1
                            print(f'Puja aceptada: {nombre} | ${precio:.2f}', flush=True)
                            publicar({r[2] for r in registrados.values()})
                        else:
                            print(f'Puja rechazada: {nombre} | ${oferta:.2f} | Actual: ${precio:.2f}', flush=True)
                        responder_puja(cid, oferta, aceptada, registrados[cid][2])
                except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, OSError):
                    continue
        finally:
            detener.set()
            hilo.join()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nSubastador detenido.')
    except OSError as e:
        print(f'Error de red: {e}')