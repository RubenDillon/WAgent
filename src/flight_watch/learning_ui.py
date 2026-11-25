from __future__ import annotations
import subprocess,sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QPushButton,QCheckBox,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QPlainTextEdit
from . import learning_store as store
class LearningPanel(QWidget):
 def __init__(self,request_factory,parent=None):
  super().__init__(parent);self.request_factory=request_factory;self.worker=None;self.log_job_id=None;v=QVBoxLayout(self)
  top=QHBoxLayout();self.allow=QCheckBox('Permitir aprendizaje y reparación');self.allow.setChecked(store.enabled());self.allow.toggled.connect(self.toggle);top.addWidget(self.allow);self.state=QLabel('Worker disponible · Ollama bajo demanda · cooldown 5 min');top.addStretch();top.addWidget(self.state);v.addLayout(top)
  f=QFormLayout();self.provider=QLineEdit('Delta');self.provider.setPlaceholderText('Delta');self.url=QLineEdit('https://www.delta.com/lac/en');self.url.setPlaceholderText('https://www.delta.com/lac/en');self.kind=QComboBox();self.kind.addItems(['LEARN']);self.kind.setEnabled(False);f.addRow('Proveedor',self.provider);f.addRow('URL inicial',self.url);f.addRow('Trabajo',self.kind);v.addLayout(f)
  actions=QHBoxLayout();add=QPushButton('Encolar trabajo');add.clicked.connect(self.enqueue);self.stop=QPushButton('Detener activo');self.stop.clicked.connect(self.stop_active);cancel=QPushButton('Cancelar seleccionado');cancel.clicked.connect(self.cancel_selected);delete=QPushButton('Borrar seleccionado');delete.clicked.connect(self.delete_selected);clear=QPushButton('Borrar finalizados');clear.clicked.connect(self.clear_finished);restart=QPushButton('Reiniciar worker');restart.clicked.connect(self.restart_worker);reset=QPushButton('Reset cola');reset.clicked.connect(self.reset_all);actions.addWidget(add);actions.addWidget(self.stop);actions.addWidget(cancel);actions.addWidget(delete);actions.addWidget(clear);actions.addWidget(restart);actions.addWidget(reset);actions.addStretch();v.addLayout(actions)
  self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['ID','Proveedor','Tipo','Estado','Prioridad','Progreso','Acción','Creado']);self.table.cellClicked.connect(self.pin_log);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);v.addWidget(self.table);self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(1000);v.addWidget(QLabel('Log del trabajo seleccionado/activo'));v.addWidget(self.log);self.worker_log=QPlainTextEdit();self.worker_log.setReadOnly(True);self.worker_log.setMaximumBlockCount(300);v.addWidget(QLabel('Log técnico del worker'));v.addWidget(self.worker_log)
  self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1000);self.launch_worker();self.refresh()
 def launch_worker(self):
  if self.worker and self.worker.poll() is None:return
  log=Path(__file__).resolve().parents[2]/'data'/'diagnostics'/'learning_worker.log';log.parent.mkdir(parents=True,exist_ok=True)
  fh=open(log,'a',buffering=1)
  self.worker=subprocess.Popen([sys.executable,'-u','-m','flight_watch.learning_worker'],cwd=str(Path(__file__).resolve().parents[2]),stdout=fh,stderr=fh,start_new_session=True)
 def reset_all(self):
  if self.worker and self.worker.poll() is None:
   self.worker.terminate()
   try:self.worker.wait(timeout=5)
   except Exception:
    try:self.worker.kill()
    except Exception:pass
  self.worker=None
  try:n=store.reset_learning_system()
  except Exception as e:QMessageBox.critical(self,'Reset aprendizaje',str(e));return
  self.log_job_id=None
  self.launch_worker();self.refresh();QMessageBox.information(self,'Reset aprendizaje',f'Cola reiniciada. Se eliminaron {n} trabajo(s).')
 def restart_worker(self):
  if self.worker and self.worker.poll() is None:
   self.worker.terminate()
   try:self.worker.wait(timeout=5)
   except Exception:
    try:self.worker.kill()
    except Exception:pass
  self.worker=None
  try:
   if hasattr(store,'interrupt_all_running'):store.interrupt_all_running('Worker reiniciado manualmente')
   elif hasattr(store,'recover_interrupted'):store.recover_interrupted()
  except Exception as e:
   QMessageBox.warning(self,'Worker',f'No pude limpiar RUNNING huérfano: {e}')
  self.launch_worker();self.refresh()
 def toggle(self,on):store.set_enabled(on);self.refresh()
 def enqueue(self):
  name=self.provider.text().strip();url=self.url.text().strip()
  if not name or not url:QMessageBox.warning(self,'Aprendizaje','Ingresá proveedor y URL.');return
  r=self.request_factory();goal={'origin':r.origin,'destination':r.destination,'departure':r.departure.isoformat(),'return_date':r.return_date.isoformat(),'ages':list(r.ages),'cabin':r.cabin}
  store.enqueue(name,url,self.kind.currentText(),goal);self.launch_worker();self.refresh()
 def stop_active(self):
  a=store.active()
  if a:store.request_cancel(a['id'])
 def cancel_selected(self):
  row=self.table.currentRow()
  if row>=0:store.cancel_queued(int(self.table.item(row,0).text()));self.refresh()
 def pin_log(self,row,col=0):
  item=self.table.item(row,0)
  if item:self.log_job_id=int(item.text());self.refresh_log()
 def refresh_log(self):
  a=store.active();jid=self.log_job_id
  if jid is not None and not any(j['id']==jid for j in store.list_jobs()):jid=None;self.log_job_id=None
  jid=jid or (a['id'] if a else None)
  if not jid:self.log.setPlainText('Sin trabajo seleccionado/activo.');return
  ev=store.events(jid)
  text='\n'.join(f"[{e['created_at']}] {e['level']}: {e['message']}" for e in ev)
  self.log.setPlainText(text)
  out=Path(__file__).resolve().parents[2]/'data'/'diagnostics'/'learning'/f'job_{jid}.log';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8')
  sb=self.log.verticalScrollBar();sb.setValue(sb.maximum())
 def delete_selected(self):
  row=self.table.currentRow()
  if row<0:return
  jid=int(self.table.item(row,0).text());ok,msg=store.delete_job(jid)
  if ok and self.log_job_id==jid:self.log_job_id=None
  if not ok:QMessageBox.information(self,'Aprendizaje',msg)
  self.refresh()
 def clear_finished(self):
  n=store.clear_finished();QMessageBox.information(self,'Aprendizaje',f'Se eliminaron {n} trabajo(s) finalizado(s) y sus logs.');self.refresh()
 def refresh(self):
  diag=store.queue_diagnostics();jobs=store.list_jobs();a=store.active();pid=self.worker.pid if self.worker and self.worker.poll() is None else 'DOWN';self.state.setToolTip(str(diag));self.state.setText(('🔵 '+a['job_type']+' '+a['provider']+' · '+str(a['progress'])+'/40') if a else (f'○ Worker PID {pid} disponible' if store.enabled() else f'⛔ Solo recolección · Worker PID {pid}'))
  self.stop.setEnabled(bool(a));self.table.setRowCount(0)
  for j in jobs:
   r=self.table.rowCount();self.table.insertRow(r);vals=[j['id'],j['provider'],j['job_type'],j['status'],j['priority'],f"{j['progress']}/{j['max_actions']}",j['current_action'] or '',j['created_at']]
   for c,x in enumerate(vals):self.table.setItem(r,c,QTableWidgetItem(str(x)))
  self.refresh_log()
 def refresh_worker_log(self):
  path=Path(__file__).resolve().parents[2]/'data'/'diagnostics'/'learning_worker.log'
  if not path.exists():self.worker_log.setPlainText('Sin learning_worker.log todavía.');return
  try:
   lines=path.read_text(errors='replace').splitlines()[-120:]
   self.worker_log.setPlainText('\n'.join(lines));sb=self.worker_log.verticalScrollBar();sb.setValue(sb.maximum())
  except Exception as e:self.worker_log.setPlainText(f'No pude leer worker log: {e}')
 def shutdown(self):
  if self.worker and self.worker.poll() is None:self.worker.terminate()
