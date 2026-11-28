import socket
import threading
import json
import math
import uuid

MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
SERVER_PORT = 5008


def main():
    servidor = socket.gethostbyname(input('IP del subastador [Enter = local 127.0.0.1]: ').strip() or '127.0.0.1')
    nombre = input('Ingresa tu nombre: ').strip()
    if not nombre or len(nombre)>80 or not nombre.isprintable():
        print('Nombre inválido.')
        return
    # connect UDP únicamente consulta la ruta local: no transmite datagramas.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as ruta:
        ruta.connect((servidor, SERVER_PORT))
        interfaz = ruta.getsockname()[0]
    cid = uuid.uuid4().hex
    listo, detener = threading.Event(), threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receptor, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as emisor:
        receptor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receptor.bind(('', MULTICAST_PORT))
        receptor.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MULTICAST_GROUP)+socket.inet_aton(interfaz))
        receptor.settimeout(0.5)
        emisor.bind((interfaz, 0))
        def enviar(tipo, **extra):
            m = dict(tipo=tipo, id=cid, nombre=nombre, servidor=servidor, **extra)
            emisor.sendto(json.dumps(m).encode(), (servidor, SERVER_PORT))
        def escuchar():
            ultima, sesion = -1, None
            while not detener.is_set():
                try:
                    datos, addr = receptor.recvfrom(4096)
                    if addr[0] != servidor:
                        continue
                    m = json.loads(datos.decode())
                    if not isinstance(m, dict):
                        continue
                    if m['tipo'] == 'RESULTADO_PUJA':
                        if m['destinatario'] == cid:
                            oferta = float(m['oferta'])
                            if m['aceptada'] is True:
                                print(f'\n[ACEPTADA] Tu puja de ${oferta:.2f} fue aceptada.', flush=True)
                            else:
                                print(f'\n[RECHAZADA] Tu puja de ${oferta:.2f} debe superar ${float(m["precio"]):.2f}.', flush=True)
                        continue
                    if m['tipo'] != 'ESTADO_SUBASTA' or m['destinatario'] not in (None, cid):
                        continue
                    if sesion != m['sesion']:
                        sesion, ultima = m['sesion'], -1
                    if m['version'] <= ultima:
                        if m['destinatario'] == cid:
                            listo.set()
                        continue
                    precio = float(m['precio'])
                    if not math.isfinite(precio):
                        continue
                    ultima = m['version']
                    print(f'\n[ACTUALIZACIÓN] Mejor oferta: ${precio:.2f} | Mejor postor: {m["postor"]}', flush=True)
                    if m['destinatario'] == cid:
                        listo.set()
                except socket.timeout:
                    continue
                except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
                    continue
                except OSError:
                    break
        hilo = threading.Thread(target=escuchar, daemon=True)
        hilo.start()
        try:
            for _ in range(3):
                enviar('REGISTRO')
                if listo.wait(2):
                    break
            else:
                print('No llegó el estado inicial multicast. Comprueba la interfaz, firewall y red virtual.')
                return
            def pujar(leer):
                while True:
                    texto = leer(f'[{nombre}] Tu puja: ').strip()
                    if not texto:
                        continue
                    try:
                        oferta = float(texto)
                        if not math.isfinite(oferta) or oferta <= 0:
                            raise ValueError
                    except ValueError:
                        print('Introduce un importe positivo válido.')
                        continue
                    enviar('PUJA', oferta=oferta)
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.patch_stdout import patch_stdout
            except ImportError:
                print('Modo básico de consola. Instala prompt_toolkit para redibujar la entrada automáticamente.')
                pujar(input)
            else:
                sesion_prompt = PromptSession()
                with patch_stdout():
                    pujar(sesion_prompt.prompt)
        finally:
            detener.set()
            hilo.join(timeout=1)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nSaliendo de la subasta...')
    except OSError as e:
        print(f'Error de red: {e}')
