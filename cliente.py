import ipaddress
import math
import os
import select
import socket
import struct
import sys
import time

MULTICAST_GROUP = "239.1.1.1"
MULTICAST_PORT = 5008
MULTICAST_TTL = 1
IP_SERVIDOR_LOCAL = "127.0.0.1"


def validar_ip_servidor(valor):
    try:
        ip = ipaddress.IPv4Address(valor.strip())
    except ipaddress.AddressValueError as exc:
        raise ValueError("Debes introducir una direccion IPv4 valida.") from exc

    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise ValueError("Introduce una direccion IPv4 unicast del subastador.")
    return str(ip)


def detectar_interfaz_local(ip_servidor):
    """Determina la interfaz local que enruta hacia la IP indicada."""
    if ip_servidor == IP_SERVIDOR_LOCAL:
        return IP_SERVIDOR_LOCAL

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sonda:
        # connect() UDP consulta la tabla de rutas; no envia datos de aplicacion.
        sonda.connect((ip_servidor, MULTICAST_PORT))
        ip_local = sonda.getsockname()[0]

    if not ip_local or ip_local == "0.0.0.0":
        raise OSError("No se pudo determinar la interfaz local de red.")

    if ip_servidor.startswith("25.") and not ip_local.startswith("25."):
        raise OSError(
            f"La ruta hacia {ip_servidor} selecciono {ip_local}, no una IP Hamachi. "
            "Comprueba que Hamachi este conectado y que ambos equipos esten "
            "en la misma red virtual."
        )

    return ip_local


def crear_socket_multicast(ip_interfaz):
    """Enlaza el puerto UDP, se une al grupo y transmite por la interfaz elegida."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", MULTICAST_PORT))

        grupo = socket.inet_aton(MULTICAST_GROUP)
        interfaz = socket.inet_aton(ip_interfaz)
        membresia = struct.pack("4s4s", grupo, interfaz)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membresia)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, interfaz)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.setblocking(False)
        return sock
    except Exception:
        sock.close()
        raise


def enviar(sock, mensaje):
    """Envia ofertas y anuncios unicamente al grupo multicast."""
    sock.sendto(
        mensaje.encode("utf-8"),
        (MULTICAST_GROUP, MULTICAST_PORT),
    )


def procesar_mensaje(data, ultimo_estado):
    """Filtra publicaciones del servidor y devuelve el texto que debe mostrarse."""
    mensaje = data.decode("utf-8", errors="replace").strip()
    if not mensaje.startswith("SERVIDOR|"):
        return ultimo_estado, None

    contenido = mensaje[len("SERVIDOR|"):]
    if contenido.startswith("ESTADO_SUBASTA|"):
        if contenido == ultimo_estado:
            return ultimo_estado, None
        ultimo_estado = contenido

    return ultimo_estado, contenido


def esperar_estado_inicial(sock, nombre):
    """Anuncia la incorporacion y espera el estado sin sondeo periodico."""
    ultimo_estado = None

    print("Suscrito al grupo multicast.")
    print("Solicitando el estado vigente mediante multicast...")

    for intento in range(3):
        if intento:
            print(f"Sin respuesta; reintentando ({intento + 1}/3)...")
        enviar(sock, f"CLIENTE|UNIR|{nombre}")
        limite = time.monotonic() + 2.0

        while time.monotonic() < limite:
            restante = max(0.0, limite - time.monotonic())
            legibles, _, _ = select.select([sock], [], [], restante)
            if not legibles:
                break
            try:
                data, origen = sock.recvfrom(2048)
            except BlockingIOError:
                continue
            ultimo_estado, contenido = procesar_mensaje(data, ultimo_estado)
            if contenido is not None:
                print(f"\n[SUBASTADOR MULTICAST desde {origen[0]}] {contenido}")
            if ultimo_estado is not None:
                return ultimo_estado

    if ultimo_estado is None:
        print(
            "No se recibio el estado inicial. Comprueba que el subastador "
            "este activo, que haya habilitado esta interfaz y que el firewall "
            "permita UDP multicast en el puerto 5008."
        )
    return ultimo_estado


def procesar_linea_oferta(sock, nombre, linea):
    """Valida y envia una linea de oferta. Devuelve False para salir."""
    texto = linea.strip()
    if texto.lower() == "salir":
        return False
    if not texto:
        print("No se ingreso ninguna oferta. Escribe un importe o 'salir'.")
        return True

    try:
        oferta = float(texto)
        if not math.isfinite(oferta) or oferta <= 0:
            raise ValueError
    except ValueError:
        print("Introduce un importe positivo valido.")
        return True

    enviar(sock, f"CLIENTE|OFERTA|{nombre}|{oferta:.2f}")
    return True


def bucle_consola_posix(sock, nombre, ultimo_estado):
    """Lee teclado y multicast en el mismo hilo; evita que la salida rompa input()."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    ajustes_originales = termios.tcgetattr(fd)
    prompt = f"[{nombre}] Tu puja: "
    buffer = ""

    def dibujar_prompt():
        sys.stdout.write("\r\x1b[2K" + prompt + buffer)
        sys.stdout.flush()

    def mostrar_evento(data, origen):
        nonlocal ultimo_estado
        nuevo_estado, contenido = procesar_mensaje(data, ultimo_estado)
        ultimo_estado = nuevo_estado
        if contenido is not None:
            # La linea que se estaba escribiendo se conserva y se vuelve a dibujar.
            sys.stdout.write("\r\x1b[2K\n")
            sys.stdout.write(
                f"[SUBASTADOR MULTICAST desde {origen[0]}] {contenido}\n"
            )
            dibujar_prompt()

    try:
        # Modo cbreak: el programa recibe teclas una a una y las dibuja.
        # Esto permite atender multicast sin competir con input() ni perder el prompt.
        tty.setcbreak(fd)
        dibujar_prompt()

        while True:
            legibles, _, _ = select.select([sock, fd], [], [], 0.2)

            if sock in legibles:
                while True:
                    try:
                        data, origen = sock.recvfrom(2048)
                    except BlockingIOError:
                        break
                    mostrar_evento(data, origen)

            if fd in legibles:
                caracter = os.read(fd, 1).decode("utf-8", errors="ignore")
                if not caracter:
                    continue

                if caracter in ("\r", "\n"):
                    linea = buffer
                    buffer = ""
                    sys.stdout.write("\r\x1b[2K\n")
                    sys.stdout.flush()
                    continuar = procesar_linea_oferta(sock, nombre, linea)
                    if not continuar:
                        return ultimo_estado
                    dibujar_prompt()
                elif caracter in ("\x7f", "\x08"):
                    buffer = buffer[:-1]
                    dibujar_prompt()
                elif caracter == "\x04":  # Ctrl+D
                    sys.stdout.write("\n")
                    return ultimo_estado
                elif caracter.isprintable():
                    buffer += caracter
                    dibujar_prompt()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, ajustes_originales)
        sys.stdout.write("\n")
        sys.stdout.flush()


def bucle_consola_windows(sock, nombre, ultimo_estado):
    """Alternativa de teclado para Windows sin bloquear la recepcion multicast."""
    import msvcrt

    prompt = f"[{nombre}] Tu puja: "
    buffer = ""
    ultima_linea = 0

    def dibujar_prompt():
        nonlocal ultima_linea
        contenido = prompt + buffer
        sys.stdout.write("\r" + contenido + " " * max(0, ultima_linea - len(contenido)))
        sys.stdout.write("\r" + contenido)
        sys.stdout.flush()
        ultima_linea = len(contenido)

    def mostrar_evento(data, origen):
        nonlocal ultimo_estado, ultima_linea
        nuevo_estado, contenido = procesar_mensaje(data, ultimo_estado)
        ultimo_estado = nuevo_estado
        if contenido is not None:
            sys.stdout.write("\r" + " " * (ultima_linea + 2) + "\r")
            print(f"[SUBASTADOR MULTICAST desde {origen[0]}] {contenido}")
            ultima_linea = 0
            dibujar_prompt()

    dibujar_prompt()
    while True:
        legibles, _, _ = select.select([sock], [], [], 0.05)
        if legibles:
            while True:
                try:
                    data, origen = sock.recvfrom(2048)
                except BlockingIOError:
                    break
                mostrar_evento(data, origen)

        if not msvcrt.kbhit():
            continue
        caracter = msvcrt.getwch()
        if caracter in ("\x00", "\xe0"):
            # Descarta el segundo codigo de teclas especiales (flechas, etc.).
            if msvcrt.kbhit():
                msvcrt.getwch()
            continue
        if caracter in ("\r", "\n"):
            linea = buffer
            buffer = ""
            sys.stdout.write("\n")
            continuar = procesar_linea_oferta(sock, nombre, linea)
            if not continuar:
                return ultimo_estado
            ultima_linea = 0
            dibujar_prompt()
        elif caracter == "\x08":
            buffer = buffer[:-1]
            dibujar_prompt()
        elif caracter == "\x03":
            raise KeyboardInterrupt
        elif caracter == "\x04":
            return ultimo_estado
        elif caracter.isprintable():
            buffer += caracter
            dibujar_prompt()


def main():
    entrada_ip = input(
        f"IP del subastador [Enter = local {IP_SERVIDOR_LOCAL}]: "
    ).strip()
    if not entrada_ip:
        entrada_ip = IP_SERVIDOR_LOCAL

    try:
        ip_servidor = validar_ip_servidor(entrada_ip)
        ip_interfaz = detectar_interfaz_local(ip_servidor)
    except (ValueError, OSError) as exc:
        print(f"No se pudo seleccionar la interfaz de red: {exc}")
        return

    nombre = input("Nombre del postor: ").strip()
    if not nombre or len(nombre) > 40 or any(
        c in nombre for c in ":|\r\n"
    ):
        print("Nombre invalido (max. 40 caracteres, sin : ni |).")
        return

    print(f"IP indicada del subastador: {ip_servidor}")
    print(f"Interfaz local seleccionada: {ip_interfaz}")
    print(f"Escucha UDP en 0.0.0.0:{MULTICAST_PORT}")
    print(f"Grupo multicast: {MULTICAST_GROUP}:{MULTICAST_PORT}")

    with crear_socket_multicast(ip_interfaz) as sock:
        try:
            ultimo_estado = esperar_estado_inicial(sock, nombre)
            if os.name == "nt":
                bucle_consola_windows(sock, nombre, ultimo_estado)
            elif sys.stdin.isatty():
                bucle_consola_posix(sock, nombre, ultimo_estado)
            else:
                print("La consola no es interactiva; no se puede leer la puja en tiempo real.")
                return
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            try:
                enviar(sock, f"CLIENTE|SALIR|{nombre}")
            except OSError:
                pass

    print("\nCliente finalizado.")


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(f"Error en la comunicacion multicast: {exc}")
        print("Verifica las interfaces y el firewall UDP.")
