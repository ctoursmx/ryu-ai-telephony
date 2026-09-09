import json

token = "EAAPcpZCdTRZBMBSZAUl0K5Vr1uOPH3tVTX2QgZCJaP63cZAR8dWXtkomwHDX85jRxHW3ZCSbTRpAElYOKDITgBMyslGJLSi8ZBuSm8reBkNpEYVqEAG3zITlSAZCBicOWZAxyTAbr99fOIGAAW1NR1FZC6ZB7sciKKs0Fjwy8hghs20KtamgAOTq1uXGZC1MztTSsoUN4wZDZD"

with open('n8n_ryu_single_workflow.json', 'r', encoding='utf-8') as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['id'] in ['get-audio-url', 'download-audio-file', 'meta-send-message']:
        params = n.get('parameters', {}).get('headerParameters', {}).get('parameters', [])
        for p in params:
            if p.get('name') == 'Authorization':
                p['value'] = f"Bearer {token}"

with open('n8n_ryu_single_workflow.json', 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print('Updated PERMANENT Meta token across all nodes in n8n_ryu_single_workflow.json!')
