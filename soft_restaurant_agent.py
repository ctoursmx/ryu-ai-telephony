# -*- coding: utf-8 -*-
"""
======================================================================
RESTAURANTE RYU - AGENTE LOCAL SOFT RESTAURANT & IMPRESORAS DE COCINA
100% Open Source, Coste Cero ($0 USD), Sin necesidad de VPN de pago.
======================================================================
Este script se ejecuta en la computadora local de Restaurante Ryu (Tequila, Jal.)
donde est? instalado Soft Restaurant 10 y las impresoras de red (192.168.1.x).
Sincroniza en tiempo real las comandas telef?nicas tomadas por la IA en Oracle Cloud.
"""

import os
import sys
import time
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [RyuPOSAgent]: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pos_agent.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("RyuPOSAgent")

VPS_URL = os.getenv("RYU_VPS_URL", "http://140.84.186.64:8000")
POS_SECRET = os.getenv("POS_BRIDGE_SECRET", "ryu_pos_secret_key_2026")
POLL_INTERVAL = float(os.getenv("POS_POLL_INTERVAL_SEC", "3.5"))


def fetch_pending_orders():
    """Consulta al VPS de Oracle Cloud por nuevas comandas tomadas por la IA."""
    url = f"{VPS_URL.rstrip('/')}/api/pos/orders/pending"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ryu-Local-POS-Agent/1.0",
            "X-POS-Token": POS_SECRET
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("orders", [])
    except urllib.error.HTTPError as e:
        logger.error(f"Error HTTP consultando VPS ({e.code}): {e.reason}")
        return []
    except urllib.error.URLError as e:
        logger.warning(f"VPS temporalmente inaccesible ({e.reason}). Reintentando...")
        return []
    except Exception as e:
        logger.error(f"Error inesperado consultando VPS: {e}")
        return []


def acknowledge_order(order_id: str):
    """Notifica al VPS que la comanda ya fue impresa e inyectada con ?xito."""
    url = f"{VPS_URL.rstrip('/')}/api/pos/orders/{order_id}/ack"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "User-Agent": "Ryu-Local-POS-Agent/1.0",
            "Content-Type": "application/json",
            "X-POS-Token": POS_SECRET
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("status") == "ok"
    except Exception as e:
        logger.error(f"Error enviando ACK para orden {order_id}: {e}")
        return False


def run_agent_loop():
    logger.info("==================================================================")
    logger.info("?? [Agente Local Soft Restaurant Ryu] Iniciado exitosamente.")
    logger.info(f"?? Conectado a VPS: {VPS_URL}")
    logger.info(f"?? Intervalo de sondeo: {POLL_INTERVAL} segundos")
    logger.info("==================================================================")

    # Importar motor de despacho local
    try:
        from soft_restaurant_bridge import dispatch_order
    except ImportError as e:
        logger.critical(f"No se pudo importar soft_restaurant_bridge: {e}")
        sys.exit(1)

    while True:
        try:
            pending_orders = fetch_pending_orders()
            if pending_orders:
                logger.info(f"?? {len(pending_orders)} comanda(s) pendiente(s) recibida(s) desde VPS.")
                for order in pending_orders:
                    order_id = order.get("order_id", "DESCONOCIDO")
                    cliente = order.get("customer_name", "Cliente")
                    total = order.get("total_amount", 0.0)
                    logger.info(f"?? Procesando comanda {order_id} | {cliente} | ${total:.2f}")

                    # 1. Inyectar en SQL Server local y disparar impresi?n ESC/POS a impresoras de cocina
                    dispatch_results = dispatch_order(order)
                    sql_res = dispatch_results.get("sql_injection", {})
                    logger.info(f" -> Soft Restaurant SQL: {sql_res.get('message', 'Completado')}")

                    # 2. Confirmar al VPS para cerrar el ciclo
                    if acknowledge_order(order_id):
                        logger.info(f"? Comanda {order_id} confirmada y archivada en VPS.")
                    else:
                        logger.warning(f"?? Comanda {order_id} procesada localmente pero fall? el ACK en VPS.")

        except KeyboardInterrupt:
            logger.info("?? Deteniendo agente local por solicitud del usuario.")
            break
        except Exception as e:
            logger.error(f"Error en ciclo de sondeo: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_agent_loop()
