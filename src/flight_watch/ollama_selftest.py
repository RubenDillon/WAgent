from __future__ import annotations
import requests
from .ollama_lifecycle import OllamaLifecycle,OLLAMA_URL

def main():
    life=OllamaLifecycle()
    try:
        life.ensure(print)
        models=life.available_models();print('models=',models)
        preferred='granite4.2:8b';model=life.resolve_model(preferred)
        if not model:raise RuntimeError('No hay modelos locales instalados')
        print('model=',model)
        r=requests.post(OLLAMA_URL+'/api/chat',json={'model':model,'stream':False,'think':False,'messages':[{'role':'user','content':'Respond only with {"action":"wait","ms":1000}'}],'options':{'temperature':0,'num_predict':80},'keep_alive':'5m'},timeout=120)
        r.raise_for_status();m=(r.json().get('message') or {});print('content=',repr(m.get('content','')[:300]),'thinking_chars=',len(m.get('thinking','') or ''))
        if not m.get('content'):raise RuntimeError('Ollama respondió sin message.content')
        print('OLLAMA_SELFTEST_OK')
    finally:
        # installer should not leave a server it started just for the probe
        life.cooldown_shutdown(print)
if __name__=='__main__':main()
