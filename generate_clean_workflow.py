import json

prompt = open('agent_prompt_ryu.md', encoding='utf-8').read()
permanent_token = "EAAPcpZCdTRZBMBSZAUl0K5Vr1uOPH3tVTX2QgZCJaP63cZAR8dWXtkomwHDX85jRxHW3ZCSbTRpAElYOKDITgBMyslGJLSi8ZBuSm8reBkNpEYVqEAG3zITlSAZCBicOWZAxyTAbr99fOIGAAW1NR1FZC6ZB7sciKKs0Fjwy8hghs20KtamgAOTq1uXGZC1MztTSsoUN4wZDZD"
phone_id = "1225604403977117"
telegram_bot = "8869418381:AAFQyF_V5hfwJ2HF5isH4WGUZ-17iTQhNzI"
telegram_chat = -5308916263

workflow = {
  "name": "Ryu - Produccion Oficial (WhatsApp + Whisper + IA + Telegram)",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "GET",
        "path": "webhook-ryu",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "node-get-webhook",
      "name": "Webhook Meta GET (Verificación)",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [400, 200]
    },
    {
      "parameters": {
        "respondWith": "text",
        "responseBody": "={{ $json.query['hub.challenge'] }}",
        "options": {}
      },
      "id": "node-get-respond",
      "name": "Responder Desafío Meta (200)",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1.1,
      "position": [640, 200]
    },
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "webhook-ryu",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "node-post-webhook",
      "name": "Webhook Meta POST (Mensajes)",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [400, 420]
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "{\"status\":\"ok\"}",
        "options": {}
      },
      "id": "node-post-respond",
      "name": "Confirmar Recepción (200 OK)",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1.1,
      "position": [640, 420]
    },
    {
      "parameters": {
        "jsCode": """// Extraer el mensaje entrante de Meta Cloud API (Texto o Audio)
const body = $input.item.json.body || $input.item.json;

if (body.entry && body.entry[0]?.changes[0]?.value?.messages) {
  const value = body.entry[0].changes[0].value;
  const message = value.messages[0];
  const contact = value.contacts ? value.contacts[0] : {};
  
  let messageText = '';
  let esAudio = false;
  let audioId = '';

  if (message.type === 'text' && message.text) {
    messageText = message.text.body || '';
  } else if (message.type === 'interactive') {
    messageText = message.interactive.button_reply?.title || message.interactive.list_reply?.title || '';
  } else if (message.type === 'audio' || message.type === 'voice') {
    esAudio = true;
    audioId = message.audio?.id || message.voice?.id || '';
  }
  
  if (!esAudio && !messageText) {
    return [];
  }

  return {
    json: {
      phoneNumberId: value.metadata?.phone_number_id || '""" + phone_id + """',
      fromNumber: message.from,
      customerName: contact.profile?.name || 'Cliente',
      messageId: message.id,
      messageText: messageText,
      es_audio: esAudio,
      audio_id: audioId,
      timestamp: message.timestamp
    }
  };
}

return [];"""
      },
      "id": "node-extract-message",
      "name": "Procesar Mensaje Entrante",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [880, 420]
    },
    {
      "parameters": {
        "conditions": {
          "boolean": [
            {
              "value1": "={{ $json.es_audio }}",
              "value2": True
            }
          ]
        }
      },
      "id": "node-check-audio",
      "name": "¿Es Mensaje de Audio?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [1120, 420]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "=https://graph.facebook.com/v20.0/{{ $json.audio_id }}",
        "sendHeaders": True,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": f"Bearer {permanent_token}"
            }
          ]
        },
        "options": {}
      },
      "id": "node-get-audio-url",
      "name": "Obtener URL de Audio Meta",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1360, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "={{ $json.url }}",
        "sendHeaders": True,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": f"Bearer {permanent_token}"
            }
          ]
        },
        "options": {
          "response": {
            "response": {
              "responseFormat": "file"
            }
          }
        }
      },
      "id": "node-download-audio",
      "name": "Descargar Audio Meta",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [1580, 300]
    },
    {
      "parameters": {
        "resource": "audio",
        "operation": "transcribe",
        "binaryPropertyName": "data",
        "options": {
          "language": "es",
          "temperature": 0.2
        }
      },
      "id": "node-whisper",
      "name": "Transcribir Audio con Whisper",
      "type": "@n8n/n8n-nodes-langchain.openAi",
      "typeVersion": 1.4,
      "position": [1800, 300],
      "credentials": {
        "openAiApi": {
          "id": "openai-cred",
          "name": "OpenAI account"
        }
      }
    },
    {
      "parameters": {
        "jsCode": """// Unificar el texto transcrito de Whisper
const transcripcion = $json.text || '';
const incoming = $('Procesar Mensaje Entrante').first().json;

return {
  json: {
    ...incoming,
    messageText: transcripcion,
    es_transcripcion: true
  }
};"""
      },
      "id": "node-unify-text",
      "name": "Unificar Texto Transcrito",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [2020, 300]
    },
    {
      "parameters": {
        "promptType": "define",
        "text": "=Hora actual en Tequila: {{ new Date().toLocaleTimeString('es-MX', { timeZone: 'America/Mexico_City', hour: '2-digit', minute: '2-digit', hour12: true }) }}\nMensaje del cliente: {{ $json.messageText }}",
        "options": {
          "systemMessage": prompt
        }
      },
      "id": "node-agent",
      "name": "Agente IA Ryu",
      "type": "@n8n/n8n-nodes-langchain.agent",
      "typeVersion": 1.7,
      "position": [2260, 420]
    },
    {
      "parameters": {
        "model": "gpt-4o-mini",
        "options": {
          "temperature": 0.2
        }
      },
      "id": "node-chat-model",
      "name": "OpenAI Chat Model",
      "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
      "typeVersion": 1,
      "position": [2160, 640],
      "credentials": {
        "openAiApi": {
          "id": "openai-cred",
          "name": "OpenAI account"
        }
      }
    },
    {
      "parameters": {
        "sessionIdType": "customKey",
        "sessionKey": "={{ $('Procesar Mensaje Entrante').first().json.fromNumber }}",
        "contextWindowLength": 15
      },
      "id": "node-memory",
      "name": "Memoria por Teléfono",
      "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
      "typeVersion": 1.3,
      "position": [2360, 640]
    },
    {
      "parameters": {
        "method": "POST",
        "url": f"=https://graph.facebook.com/v20.0/{{{{ $('Procesar Mensaje Entrante').first().json.phoneNumberId || '{phone_id}' }}}}/messages",
        "sendHeaders": True,
        "headerParameters": {
          "parameters": [
            {
              "name": "Authorization",
              "value": f"Bearer {permanent_token}"
            },
            {
              "name": "Content-Type",
              "value": "application/json"
            }
          ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": """={{ JSON.stringify({
  messaging_product: 'whatsapp',
  recipient_type: 'individual',
  to: $('Procesar Mensaje Entrante').first().json.fromNumber,
  type: 'text',
  text: {
    preview_url: false,
    body: (() => {
      let raw = $json.output || '';
      if (raw.includes('[CLIENTE]')) {
        let m = raw.match(/\\[CLIENTE\\]([\\s\\S]*?)\\[\\/CLIENTE\\]/i);
        if (m && m[1]) return m[1].trim();
      }
      return raw.replace(/\\[COMANDA\\][\\s\\S]*?\\[\\/COMANDA\\]/gi, '').replace(/\\[CLIENTE\\]|\\[\\/CLIENTE\\]/gi, '').trim();
    })()
  }
}) }}"""
      },
      "id": "node-send-whatsapp",
      "name": "Responder por WhatsApp Meta",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [2580, 300]
    },
    {
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
      "position": [2580, 540],
      "id": "node-check-confirmed",
      "name": "¿Pedido Confirmado?"
    },
    {
      "parameters": {
        "jsCode": """// Formateador de Comanda para Telegram Cocina Ryu
const incoming = $('Procesar Mensaje Entrante').first().json;
const agentOutput = $json.output || '';

const now = new Date();
const fechaStr = now.toLocaleDateString('es-MX', { timeZone: 'America/Mexico_City', day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + now.toLocaleTimeString('es-MX', { timeZone: 'America/Mexico_City', hour: '2-digit', minute: '2-digit', hour12: true });

const customerName = incoming.customerName || 'Cliente';
const customerPhone = incoming.fromNumber || '';

// Extraer bloque de comanda
let comandaContent = '';
const match = agentOutput.match(/\\[COMANDA\\]([\\s\\S]*?)\\[\\/COMANDA\\]/i);
if (match && match[1]) {
  comandaContent = match[1].trim();
} else {
  comandaContent = agentOutput
    .replace(/¡Excelente![\\s\\S]*?minutos\\./gi, '')
    .replace(/¡Muchas gracias[\\s\\S]*?Ryu!/gi, '')
    .replace(/\\[CLIENTE\\][\\s\\S]*?\\[\\/CLIENTE\\]/gi, '')
    .trim();
}

if (!comandaContent) {
  comandaContent = agentOutput;
}

let ticket = `🍣 <b>NUEVO PEDIDO - RESTAURANTE RYU</b> 🍱\\n`;
ticket += `━━━━━━━━━━━━━━━━━━━━━\\n`;
ticket += `📅 <b>Fecha:</b> ${fechaStr}\\n`;
ticket += `👤 <b>Cliente:</b> ${customerName}\\n`;
ticket += `📱 <b>Teléfono:</b> +${customerPhone}\\n`;
ticket += `━━━━━━━━━━━━━━━━━━━━━\\n`;
ticket += `${comandaContent}\\n`;
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
      "position": [2800, 540],
      "id": "node-format-ticket",
      "name": "Formatear Comanda Exacta"
    },
    {
      "parameters": {
        "method": "POST",
        "url": f"https://api.telegram.org/bot{telegram_bot}/sendMessage",
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
        "jsonBody": "={{ JSON.stringify({\n  chat_id: " + str(telegram_chat) + ",\n  text: $json.telegramMessage,\n  parse_mode: 'HTML'\n}) }}",
        "options": {}
      },
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [3020, 540],
      "id": "node-send-telegram",
      "name": "Enviar Telegram Cocina"
    }
  ],
  "connections": {
    "Webhook Meta GET (Verificación)": {
      "main": [
        [
          {
            "node": "Responder Desafío Meta (200)",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Webhook Meta POST (Mensajes)": {
      "main": [
        [
          {
            "node": "Confirmar Recepción (200 OK)",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Confirmar Recepción (200 OK)": {
      "main": [
        [
          {
            "node": "Procesar Mensaje Entrante",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Procesar Mensaje Entrante": {
      "main": [
        [
          {
            "node": "¿Es Mensaje de Audio?",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "¿Es Mensaje de Audio?": {
      "main": [
        [
          {
            "node": "Obtener URL de Audio Meta",
            "type": "main",
            "index": 0
          }
        ],
        [
          {
            "node": "Agente IA Ryu",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Obtener URL de Audio Meta": {
      "main": [
        [
          {
            "node": "Descargar Audio Meta",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Descargar Audio Meta": {
      "main": [
        [
          {
            "node": "Transcribir Audio con Whisper",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Transcribir Audio con Whisper": {
      "main": [
        [
          {
            "node": "Unificar Texto Transcrito",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Unificar Texto Transcrito": {
      "main": [
        [
          {
            "node": "Agente IA Ryu",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "OpenAI Chat Model": {
      "ai_languageModel": [
        [
          {
            "node": "Agente IA Ryu",
            "type": "ai_languageModel",
            "index": 0
          }
        ]
      ]
    },
    "Memoria por Teléfono": {
      "ai_memory": [
        [
          {
            "node": "Agente IA Ryu",
            "type": "ai_memory",
            "index": 0
          }
        ]
      ]
    },
    "Agente IA Ryu": {
      "main": [
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
    },
    "¿Pedido Confirmado?": {
      "main": [
        [
          {
            "node": "Formatear Comanda Exacta",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Formatear Comanda Exacta": {
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
  }
}

with open('n8n_ryu_PRODUCCION_OFICIAL.json', 'w', encoding='utf-8') as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)

print('Generated clean n8n_ryu_PRODUCCION_OFICIAL.json!')
