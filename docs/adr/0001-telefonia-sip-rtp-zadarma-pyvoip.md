# ADR-0001: Enlace Telefónico SIP/RTP Directo con Zadarma y pyVoIP Parcheado

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-01
* **Decisores**: Arquitectura de Telefonía Ryu
* **Contexto Técnico**: `sip_telephony_service.py` / Troncal Zadarma VoIP DID `+52 33 8526 1250`

---

## 1. Contexto y Planteamiento del Problema

El restaurante Ryu requiere recibir y contestar en tiempo real llamadas telefónicas directas desde la red pública de telefonía (PSTN) en Tequila, Jalisco (~1,700 llamadas por semana).

Tradicionalmente, las soluciones de telefonía de IA se implementan a través de proveedores CPaaS intermediarios en la nube como Twilio Voice o Plivo mediante WebSockets, o montando servidores Asterisk / FreePBX completos. Sin embargo:
1. **Twilio/Plivo**: Imponen tarifas por minuto de telefonía ($0.015 - $0.035 USD/min), lo que para 1,700 llamadas semanales de 3 minutos representaría un costo de más de **$300 - $700 USD mensuales** solo por el transporte de voz.
2. **Asterisk / FreePBX**: Consume cientos de megabytes de memoria RAM, añade latencias de puente (bridge) y complejidad de configuración para un solo conmutador.

---

## 2. Factores Clave de Decisión

* **Cero costo por minuto de telefonía intermediaria**: Mantener la línea en Zadarma con tarifa fija mensual.
* **Control a nivel de trama RTP**: Acceso a los bytes crudos del flujo de audio PCM/A-law en memoria sin conversión a WebSockets o WebRTC en la nube.
* **Latencia ultra-baja**: Respuesta y envío inmediato de audio en intervalos de 20 ms (50 paquetes por segundo).
* **Manejo de SIP NAT Traversal**: Capacidad de registrar y mantener viva la extensión SIP en el servidor de producción.

---

## 3. Opciones Consideradas

### Opción A: Twilio Voice API / Twilio Media Streams (WebSocket)
* **Ventajas**: Fácil de conectar con Python mediante WebSockets.
* **Desventajas**: Costos exorbitantes por minuto, latencia adicional por ruteo en servidores de EE.UU.

### Opción B: Servidor PBX Asterisk / Kamailio intermedio
* **Ventajas**: Estándar corporativo de telecomunicaciones.
* **Desventajas**: Mayor huella de memoria en el VPS, configuración compleja de dialplans y retrasos de audio por puentes internos.

### Opción C: Cliente SIP Nativo en Python (`pyVoIP`) con Parches de Alto Rendimiento (Elegida)
* **Ventajas**:
  - Enlace SIP directo UDP en puerto 5060 entre el servidor VPS y el proxy `sip1.zadarma.com`.
  - Acceso directo a los paquetes RTP en tiempo real.
  - Cero dependencias externas pesadas.
* **Desventajas**:
  - La biblioteca `pyVoIP` estándar presenta problemas de jitter y pausas en hilos de transmisión.
  - Requiere aplicar parches de temporizador multimedia (1 ms en Windows, hilos de alta prioridad en Linux), soporte RFC 4961 (RTP simétrico) y colas thread-safe.

---

## 4. Decisión Adoptada

Se decidió implementar la **Opción C**: utilizar un cliente SIP directo en Python sobre `pyVoIP`, aplicando parches a nivel de clase para:
1. **Temporizador de alta precisión (1 ms)** para garantizar un flujo continuo a 50 pps (160 bytes cada 20 ms).
2. **RTP Monotónico Simétrico**: Envío y recepción por el mismo puerto UDP para atravesar cortafuegos y NAT sin cortes.
3. **Detector de Fin de Flujo**: Vigilancia continua de recepción de audio para colgar inmediatamente cuando el cliente cuelga la llamada.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Costo mensual de telefonía reducido a la tarifa fija del proveedor DID de Zadarma (~$5 USD/mes).
* Latencia de transporte de audio reducida a menos de **30 milisegundos**.
* Capacidad de ejecutar el servicio completo en un contenedor ligero de Docker en el VPS.

### Impactos Negativos y Mitigación
* **Sensibilidad al Jitter de Red**: Resuelto mediante el búfer circular monotónico y el watchdog de reconexión SIP (`sip1.zadarma.com`).

---

## 6. Cumplimiento y Verificación

* Registro exitoso verificado en logs de arranque con respuesta `SIP/2.0 200 OK`.
* Verificación continua con el script `verify_zadarma_now.py`.
