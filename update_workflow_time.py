import json

with open('n8n_ryu_single_workflow.json', 'r', encoding='utf-8') as f:
    wf = json.load(f)

prompt = open('agent_prompt_ryu.md', encoding='utf-8').read()

for n in wf['nodes']:
    if n['id'] == 'ai-agent-ryu':
        n['parameters']['options']['systemMessage'] = prompt
        n['parameters']['text'] = "=Hora actual en Tequila: {{ new Date().toLocaleTimeString('es-MX', { timeZone: 'America/Mexico_City', hour: '2-digit', minute: '2-digit', hour12: true }) }}\nMensaje del cliente: {{ $json.messageText }}"

with open('n8n_ryu_single_workflow.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print('Updated prompt and dynamic local time in n8n_ryu_single_workflow.json!')
