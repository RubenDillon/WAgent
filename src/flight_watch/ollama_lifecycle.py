from __future__ import annotations
import os,shutil,signal,subprocess,time
from typing import Callable
import requests
OLLAMA_URL=os.getenv('OLLAMA_HOST','http://localhost:11434')
FALLBACK_PATHS=('/opt/homebrew/bin/ollama','/usr/local/bin/ollama','/Applications/Ollama.app/Contents/Resources/ollama')
READY_TIMEOUT=30;STOP_TIMEOUT=8
class OllamaLifecycle:
 def __init__(self):self._proc=None;self._owned=False
 @staticmethod
 def is_running():
  try:return requests.get(f'{OLLAMA_URL}/api/tags',timeout=2).ok
  except requests.RequestException:return False
 @staticmethod
 def _binary():return shutil.which('ollama') or next((p for p in FALLBACK_PATHS if os.path.exists(p)),None)
 def ensure(self,log:Callable[[str],None]=print):
  if self.is_running():log('Ollama ya estaba corriendo; se reutiliza.');return False
  binary=self._binary()
  if not binary:raise RuntimeError('No se encontró Ollama en PATH, /opt/homebrew/bin, /usr/local/bin ni Ollama.app.')
  self._proc=subprocess.Popen([binary,'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);self._owned=True;log(f'Ollama iniciado por Flight Watch (PID {self._proc.pid}).')
  deadline=time.monotonic()+READY_TIMEOUT
  while time.monotonic()<deadline:
   if self.is_running():log('Ollama API lista.');return True
   if self._proc.poll() is not None:raise RuntimeError('Ollama se cerró al arrancar. Ejecutá ollama serve para diagnosticar.')
   time.sleep(.5)
  raise RuntimeError('Ollama no respondió dentro de 30 segundos.')
 def available_models(self):
  try:return [x.get('name','') for x in requests.get(f'{OLLAMA_URL}/api/tags',timeout=3).json().get('models',[])]
  except Exception:return []
 def resolve_model(self,preferred):
  models=self.available_models()
  if preferred in models:return preferred
  base=preferred.split(':')[0].lower()
  same=[m for m in models if m.lower().split(':')[0]==base]
  if same:return same[0]
  # Prefer Granite if installed; otherwise first local model. Never pull automatically.
  granite=[m for m in models if 'granite' in m.lower()]
  if granite:return granite[0]
  return models[0] if models else None
 def unload_models(self,log:Callable[[str],None]=print):
  try:
   loaded=requests.get(f'{OLLAMA_URL}/api/ps',timeout=3).json().get('models',[])
   for m in loaded:
    name=m.get('name')
    if name:
     requests.post(f'{OLLAMA_URL}/api/generate',json={'model':name,'keep_alive':0},timeout=15);log(f'Modelo {name} descargado de memoria.')
  except Exception:pass
 def cooldown_shutdown(self,log:Callable[[str],None]=print):
  self.unload_models(log)
  if self._owned and self._proc and self._proc.poll() is None:
   try:os.killpg(self._proc.pid,signal.SIGTERM);self._proc.wait(timeout=STOP_TIMEOUT)
   except subprocess.TimeoutExpired:os.killpg(self._proc.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   log('Ollama detenido por Flight Watch tras cooldown.')
  self._proc=None;self._owned=False
