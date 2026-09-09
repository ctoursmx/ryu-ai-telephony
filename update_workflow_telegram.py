import json

with open('n8n_ryu_single_workflow.json', 'r', encoding='utf-8') as f:
    wf = json.load(f)

# Ensure nodes are clean
wf['nodes'] = [n for n in wf['nodes'] if n['id'] not in ['tool-telegram-inline', 'send-telegram-kitchen', 'format-kitchen-ticket', 'check-order-confirmed']]

# 1. '¿Pedido Confirmado?' IF node (checks for 'enviado a cocina')
if_node = {
  "parameters": {
    "conditions": {
      "options": {
        "caseSensitive": False,
        "leftValue": "",
        "typeValidation": "strict"
      },
      "conditions": [
        {
          "id": "c_confirmado",
          "leftValue": "={{ $json.output }}",
          "rightValue": "enviado a cocina",
          "operator": {
            "type": "string",
            "operation": "contains"
          }
        }
      ],
      "combinator": "and"
    },
    "options": {}
  },
  "type": "n8n-nodes-base.if",
  "typeVersion": 2,
  "position": [2180, 420],
  "id": "check-order-confirmed",
  "name": "¿Pedido Confirmado?"
}

# 2. 'Formatear Comanda Exacta' Code Node
format_code_node = {
  "parameters": {
    "jsCode": """// Formateador de Comanda para Telegram Cocina Ryu
const incoming = $('Procesar Mensaje Entrante').first().json;
const agentOutput = $json.output || '';

const now = new Date();
const fechaStr = now.toLocaleDateString('es-MX', { timeZone: 'America/Mexico_City', day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + now.toLocaleTimeString('es-MX', { timeZone: 'America/Mexico_City', hour: '2-digit', minute: '2-digit', hour12: true });

const customerName = incoming.customerName || 'Cliente';
const customerPhone = incoming.fromNumber || '3741141405';

// Limpiar frases de saludo y despedida para dejar solo los datos de la comanda
let cleanDetails = agentOutput
  .replace(/¡Excelente![\\s\\S]*?minutos\\./gi, '')
  .replace(/¡Muchas gracias[\\s\\S]*?Ryu!/gi, '')
  .replace(/\\[CLIENTE\\][\\s\\S]*?\\[\\/CLIENTE\\]/gi, '')
  .replace(/\\[COMANDA\\]|\\[\\/COMANDA\\]/gi, '')
  .trim();

if (!cleanDetails) {
  cleanDetails = agentOutput;
}

let ticket = `🍣 <b>NUEVO PEDIDO - RESTAURANTE RYU</b> 🍱\\n`;
ticket += `━━━━━━━━━━━━━━━━━━━━━\\n`;
ticket += `📅 <b>Fecha:</b> ${fechaStr}\\n`;
ticket += `👤 <b>Cliente:</b> ${customerName}\\n`;
ticket += `📱 <b>Teléfono:</b> +${customerPhone}\\n`;
ticket += `━━━━━━━━━━━━━━━━━━━━━\\n`;
ticket += `${cleanDetails}\\n`;
ticket += `━━━━━━━━━━━━━━━━━━━━━\\n`;
ticket += `⏳ <b>Estado:</b> 🟡 En Espera de Preparación`;

return {
  json: {
    telegramMessage: ticket
  }
};"""
  },
  "type": "n8n-nodes-base.code",
  "typeVersion": 2,
  "position": [2400, 420],
  "id": "format-kitchen-ticket",
  "name": "Formatear Comanda Exacta"
}

# 3. 'Enviar Telegram Cocina' HTTP Request node
tg_node = {
  "parameters": {
    "method": "POST",
    "url": "https://api.telegram.org/bot8869418381:AAFQyF_V5hfwJ2HF5isH4WGUZ-17iTQhNzI/sendMessage",
    "sendHeaders": True,
    "headerParameters": {
      "parameters": [
        {
          "name": "Content-Type",
          "value": "application/json"
        }
      ]
    },
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({\n  chat_id: -5308916263,\n  text: $json.telegramMessage,\n  parse_mode: 'HTML'\n}) }}",
    "options": {}
  },
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [2620, 420],
  "id": "send-telegram-kitchen",
  "name": "Enviar Telegram Cocina"
}

wf['nodes'].extend([if_node, format_code_node, tg_node])

# Configure connections
if 'Herramienta Enviar a Telegram (Inline)' in wf['connections']:
    del wf['connections']['Herramienta Enviar a Telegram (Inline)']

wf['connections']['Agente IA Ryu']['main'] = [
  [
    {
      "node": "Responder por WhatsApp Meta",
      "type": "main",
      "index": 0
    },
    {
      "node": "¿Pedido Confirmado?",
      "type": "main",
      "index": 0
    }
  ]
]

wf['connections']['¿Pedido Confirmado?'] = {
  "main": [
    [
      {
        "node": "Formatear Comanda Exacta",
        "type": "main",
        "index": 0
      }
    ]
  ]
}

wf['connections']['Formatear Comanda Exacta'] = {
  "main": [
    [
      {
        "node": "Enviar Telegram Cocina",
        "type": "main",
        "index": 0
      }
    ]
  ]
}

if 'ai_tool' in wf['connections']['Agente IA Ryu']:
    del wf['connections']['Agente IA Ryu']['ai_tool']

with open('n8n_ryu_single_workflow.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print('Definitive workflow saved successfully!')
