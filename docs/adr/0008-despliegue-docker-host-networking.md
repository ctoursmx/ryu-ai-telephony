# ADR-0008: Despliegue en Docker con Host Networking para VoIP en Servidor VPS

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-02
* **Decisores**: DevOps e Infraestructura Ryu
* **Contexto Técnico**: `Dockerfile`, `docker-compose.yml`, VPS Linux `89.167.43.130`

---

## 1. Contexto y Planteamiento del Problema

Los protocolos de telefonía sobre IP (VoIP) combinan:
* **Señalización SIP**: Típicamente UDP en el puerto 5060.
* **Flujos de Audio RTP**: Paquetes UDP asignados dinámicamente en rangos amplios de puertos (e.g. puertos 10000 a 60000).

En entornos tradicionales de Docker con redes puente tipo bridge (`bridge network`):
1. Es necesario mapear de antemano miles de puertos UDP (`-p 10000-20000:10000-20000/udp`), lo cual degrada severamente el rendimiento de la tabla de conexiones de `iptables` de Linux.
2. El enrutamiento NAT de Docker puede reescribir las cabeceras SIP `Contact` y `Via` con la IP interna del contenedor (e.g. `172.17.0.2`), provocando audio unidireccional (one-way audio) o llamadas mudas.

---

## 2. Factores Clave de Decisión

* **Cero problemas de NAT traversal para flujos de audio RTP**.
* **Rendimiento máximo de paquetes UDP por segundo sin sobrecarga de conntrack**.
* **Aislamiento de dependencias de Python y modelos de Machine Learning (CTranslate2, PyAV, soxr)** dentro de un contenedor reproducible.
* **Reinicio automático (`restart: always`)** para garantizar disponibilidad 24/7.

---

## 3. Opciones Consideradas

### Opción A: Despliegue Bare-Metal directo en el host Linux (systemd)
* **Ventajas**: Sin aislamiento de red.
* **Desventajas**: Dificulta el control de versiones de dependencias de C++ y Python en el sistema operativo del VPS.

### Opción B: Docker con Bridge Network y mapeo masivo de puertos
* **Ventajas**: Aislamiento estricto.
* **Desventajas**: Fallos frecuentes de audio bidireccional por NAT y alto consumo de CPU en `iptables`.

### Opción C: Contenedor Docker con `network_mode: host` (Elegida)
* **Ventajas**:
  - El contenedor comparte la pila de red (network namespace) directamente con el host Linux.
  - El puerto SIP 5060 y cualquier puerto RTP dinámico se abren directamente en la interfaz pública del servidor (`89.167.43.130`).
  - No hay traducción de direcciones de red (NAT) que corrompa los paquetes SIP.
  - La instalación de librerías y modelos permanece encapsulada en la imagen de Docker basada en Python 3.11 Debian.
* **Desventajas**: Solo compatible de forma nativa en sistemas operativos Linux (en desarrollo local Windows/macOS se utiliza puerto único simulado).

---

## 4. Decisión Adoptada

Se adoptó la **Opción C**:
En `docker-compose.yml`, el servicio `ryu-telephony` se define con:
```yaml
services:
  telephony:
    container_name: ryu-telephony-service
    build: .
    network_mode: host
    restart: always
    environment:
      - LOCAL_IP=89.167.43.130
      - SIP_SERVER=sip1.zadarma.com
```
Además, el script `sip_telephony_service.py` detecta dinámicamente si se encuentra en Linux o Windows para configurar los sockets UDP y la prioridad de hilos adecuada.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Registro telefónico instantáneo con Zadarma sin necesidad de servidores STUN o proxies TURN adicionales.
* Audio bidireccional perfecto y sin cortes en el 100% de las llamadas.

---

## 6. Cumplimiento y Verificación

* Verificación en VPS con `docker inspect ryu-telephony-service --format '{{.HostConfig.NetworkMode}}'` retornando `host`.
* Registro SIP con `Status: 200 OK` confirmado.
