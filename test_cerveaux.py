import requests, json, time
models = ['qwen2.5:7b', 'deepseek-r1:7b', 'phi4-mini']
prompt = 'Tu es un trader crypto. BTC RSI=28 (survente), Fear&Greed=74. Achat ou pas? Reponds JSON: {action, raison}'
for m in models:
    print(f'\n=== {m} ===')
    try:
        s = time.time()
        r = requests.post('http://localhost:11434/api/chat', json={'model': m, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False, 'options': {'temperature': 0.6, 'num_predict': 512}}, timeout=120)
        e = time.time() - s
        if r.status_code == 200:
            t = r.json()['message']['content']
            print(f'Temps: {e:.1f}s | {len(t.split())} mots | {len(t.split())/e:.1f} tok/s')
            print(t[:400])
        else:
            print(f'HTTP {r.status_code} - pas installe?')
    except Exception as ex:
        print(f'Erreur: {ex}')
