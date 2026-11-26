import ipaddress
import math
import os
import socket
import struct
import subprocess

# Parametros compartidos por servidor y clientes.
MULTICAST_GROUP = "239.1.1.1"
MULTICAST_PORT = 5008
MULTICAST_TTL = 1
BIND_IP = "0.0.0.0"  # Escucha en todas las interfaces IPv4.

precio_actual = 20.0
mejor_postor = "Ninguno"


def detectar_interfaces_ipv4():
    """Devuelve las IPv4 locales, sin pedir al usuario la IP de Hamachi."""
    
    direcciones = {"127.0.0.1"}

    if os.name == "nt":
        comando = (
            "Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty IPAddress"
        )
        try:
            resultado = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", comando],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if resultado.returncode == 0:
                for linea in resultado.stdout.splitlines():
                    candidato = linea.strip()
                    try:
                        ip = ipaddress.IPv4Address(candidato)
                    except ipaddress.AddressValueError:
                        continue
                    if not ip.is_unspecified and not ip.is_multicast:
                        direcciones.add(str(ip))
        except (OSError, subprocess.SubprocessError):
            pass

    # Alternativa opcional: psutil enumera adaptadores de forma multiplataforma.
    try:
        import psutil  # No es obligatorio instalarlo.

        for datos in psutil.net_if_addrs().values():
            for dato in datos:
                if dato.family == socket.AF_INET:
                    try:
                        ip = ipaddress.IPv4Address(dato.address)
                    except ipaddress.AddressValueError:
                        continue
                    if not ip.is_unspecified and not ip.is_multicast:
                        direcciones.add(str(ip))
    except (ImportError, OSError, AttributeError):
        pass

    # Ultimo respaldo para sistemas donde no se pudo enumerar adaptadores.
    if len(direcciones) == 1:
        try:
            for info in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM
            ):
                candidato = info[4][0]
                try:
                    ip = ipaddress.IPv4Address(candidato)
                except ipaddress.AddressValueError:
                    continue
                if not ip.is_unspecified and not ip.is_multicast:
                    direcciones.add(str(ip))
        except OSError:
            pass

    # Orden determinista: loopback primero y el resto ordenado.
    resto = sorted(ip for ip in direcciones if ip != "127.0.0.1")
    return ["127.0.0.1", *resto]


def estado():
    return (
        f"ESTADO_SUBASTA|Precio actual: ${precio_actual:.2f}, "
        f"mejor postor: {mejor_postor}"
    )


def crear_socket_receptor(interfaces):
    """Escucha en el puerto compartido y se suscribe al grupo por cada interfaz."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    interfaces_suscritas = []
    errores = []

    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((BIND_IP, MULTICAST_PORT))

        grupo = socket.inet_aton(MULTICAST_GROUP)
        for ip_interfaz in interfaces:
            membresia = struct.pack("4s4s", grupo, socket.inet_aton(ip_interfaz))
            try:
                sock.setsockopt(
                    socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membresia
                )
                interfaces_suscritas.append(ip_interfaz)
            except OSError as exc:
                errores.append((ip_interfaz, exc))

        if not interfaces_suscritas:
            raise OSError(
                "No se pudo unir al grupo multicast en ninguna interfaz IPv4."
            )

        return sock, interfaces_suscritas, errores
    except Exception:
        sock.close()
        raise


def crear_emisores_multicast(interfaces):
    """Crea un emisor por interfaz para publicar también hacia Hamachi."""
    emisores = []
    errores = []

    for ip_interfaz in interfaces:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(ip_interfaz),
            )
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            emisores.append((ip_interfaz, sock))
        except OSError as exc:
            sock.close()
            errores.append((ip_interfaz, exc))

    if not emisores:
        raise OSError("No se pudo configurar ningun emisor multicast IPv4.")

    return emisores, errores


def main():
    global precio_actual, mejor_postor

    interfaces = detectar_interfaces_ipv4()
    destino = (MULTICAST_GROUP, MULTICAST_PORT)

    receptor, interfaces_suscritas, errores_receptor = crear_socket_receptor(
        interfaces
    )
    emisores, errores_emisor = crear_emisores_multicast(interfaces_suscritas)

    try:
        def publicar(mensaje):
            """Publica por las interfaces habilitadas, pero registra un solo evento."""
            paquete = f"SERVIDOR|{mensaje}".encode("utf-8")
            envios_ok = 0
            fallos = []

            # Se transmite por cada interfaz para alcanzar clientes de la LAN,
            # La consola informa una sola vez por publicacion multicast.
            for ip_interfaz, emisor in emisores:
                try:
                    emisor.sendto(paquete, destino)
                    envios_ok += 1
                except OSError as exc:
                    fallos.append(f"{ip_interfaz}: {exc}")

            if envios_ok:
                print(f"[MULTICAST -> {MULTICAST_GROUP}:{MULTICAST_PORT}] {mensaje}")
            if fallos:
                print("[AVISO MULTICAST] Fallos de envio: " + " | ".join(fallos))
            if not envios_ok:
                print("[ERROR MULTICAST] No se pudo transmitir el mensaje por ninguna interfaz.")

        print("\nSubastador iniciado.")
        print(f"Escucha UDP en {BIND_IP}:{MULTICAST_PORT}")
        print(f"Grupo multicast: {MULTICAST_GROUP}:{MULTICAST_PORT}")
        print("Interfaces IPv4 detectadas: " + ", ".join(interfaces))
        print("Interfaces suscritas al grupo: " + ", ".join(interfaces_suscritas))

        if errores_receptor:
            resumen = " | ".join(
                f"{ip}: {exc}" for ip, exc in errores_receptor
            )
            print("[AVISO DE SUSCRIPCION] " + resumen)
        if errores_emisor:
            resumen = " | ".join(
                f"{ip}: {exc}" for ip, exc in errores_emisor
            )
            print("[AVISO DE EMISION] " + resumen)

        print("Subasta abierta.")
        publicar(estado())

        while True:
            data, addr = receptor.recvfrom(2048)

            try:
                mensaje = data.decode("utf-8").strip()

                # Ignora las publicaciones propias del servidor.
                if not mensaje.startswith("CLIENTE|"):
                    continue

                partes = mensaje.split("|", 3)
                if len(partes) < 3:
                    raise ValueError("Formato de mensaje incompleto")

                comando = partes[1]
                nombre = partes[2].strip()

                if not nombre or len(nombre) > 40 or any(
                    c in nombre for c in ":|\n\r"
                ):
                    raise ValueError("Nombre de postor invalido")

                if comando == "UNIR":
                    print(f"Cliente conectado: {nombre} desde {addr}")
                    # El estado vigente se difunde al grupo para que el nuevo
                    # cliente lo reciba; no se envian respuestas unicast.
                    publicar(estado())
                    continue

                if comando == "SALIR":
                    print(f"Cliente desconectado: {nombre} desde {addr}")
                    continue

                if comando != "OFERTA" or len(partes) != 4:
                    raise ValueError("Comando multicast desconocido o incompleto")

                oferta = float(partes[3])
                if not math.isfinite(oferta) or oferta <= 0:
                    raise ValueError(
                        "La oferta debe ser un numero positivo y finito"
                    )

                if oferta <= precio_actual:
                    publicar(
                        f"RECHAZADA|{nombre}|Tu oferta ${oferta:.2f} debe superar "
                        f"${precio_actual:.2f}"
                    )
                    print(f"Oferta rechazada: {nombre} (${oferta:.2f})")
                    continue

                precio_actual, mejor_postor = oferta, nombre
                publicar(f"ACEPTADA|{nombre}|Oferta de ${oferta:.2f} aceptada")
                print(f"Nueva oferta: {nombre} (${oferta:.2f})")
                publicar(estado())

            except (UnicodeError, ValueError) as exc:
                publicar(f"ERROR|{exc}")
                print(f"Mensaje invalido desde {addr}: {exc}")

    finally:
        receptor.close()
        for _, emisor in emisores:
            emisor.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSubastador detenido.")
    except OSError as exc:
        print(f"No se pudo iniciar el subastador multicast: {exc}")
        print(f"Comprueba las interfaces y el puerto UDP {MULTICAST_PORT}.")
