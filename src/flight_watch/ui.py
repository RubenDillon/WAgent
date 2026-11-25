import sys,subprocess,uuid
from pathlib import Path
from datetime import datetime,date
from PyQt6.QtCore import QDate,pyqtSignal,QObject
from PyQt6.QtWidgets import *
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .domain import SearchRequest
from .providers import AlmundoProvider
from .agent import Agent
from . import database
from .learning_ui import LearningPanel
from .scoring import signal
class Bus(QObject):status=pyqtSignal(str);log=pyqtSignal(object,str);obs=pyqtSignal(object)
class HistoryChart(FigureCanvasQTAgg):
 def __init__(self):self.fig=Figure(figsize=(10,4),tight_layout=True);self.ax=self.fig.add_subplot(111);super().__init__(self.fig)
 def render(self,a):
  self.ax.clear();self.ax.set_title('Mejor precio observado por ciclo');self.ax.set_ylabel('USD');self.ax.grid(True,alpha=.25)
  if a:
   x=[datetime.fromisoformat(r['observed_at']) for r in a['rows']];y=[r['price'] for r in a['rows']];self.ax.plot(x,y,marker='o',linewidth=1.2,color='#888',alpha=.5,label='Mercado observado')
   for provider,color in [('almundo','#1769aa'),('aerolineas','#d71920')]:
    rr=[r for r in a['rows'] if r.get('provider')==provider]
    if rr:self.ax.plot([datetime.fromisoformat(r['observed_at']) for r in rr],[r['price'] for r in rr],marker='o',linewidth=2,color=color,label=provider.title())
   levels=[('P10',a['p10'],'#16863f'),('P25',a['p25'],'#5a9e41'),('Mediana',a['median'],'#c28b00'),('P75',a['p75'],'#bd4c32')]
   for name,val,color in levels:self.ax.axhline(val,ls='--',linewidth=1,color=color,label=f'{name} {val:.0f}')
   self.ax.scatter([x[-1]],[y[-1]],s=75,zorder=5,label=f'Actual {y[-1]:.0f}');self.ax.legend(ncol=3,fontsize=8);self.fig.autofmt_xdate()
  else:self.ax.text(.5,.5,'Todavia no hay historial propio',ha='center',va='center',transform=self.ax.transAxes)
  self.draw_idle()
class Window(QWidget):
 def __init__(self):
  super().__init__();self.setWindowTitle('Flight Watch Agent 0.13.12post2post1post1');self.resize(1500,900);self.bus=Bus();self.bus.status.connect(self.status_set);self.bus.log.connect(self.log_add);self.bus.obs.connect(self.observed);self.agent=Agent(self.bus.status.emit,self.bus.log.emit,self.bus.obs.emit);self.last=None
  root=QVBoxLayout(self);bar=QHBoxLayout();self.status=QLabel('● DETENIDO');bar.addWidget(self.status);bar.addStretch();self.activity=QLabel('Sin actividad');bar.addWidget(self.activity);root.addLayout(bar)
  f=QFormLayout();self.o=QLineEdit('EZE');self.d=QLineEdit('FCO');self.dep=QDateEdit(QDate(2027,7,17));self.dep.setCalendarPopup(True);self.ret=QDateEdit(QDate(2027,7,29));self.ret.setCalendarPopup(True);self.age=QSpinBox();self.age.setRange(0,120);self.age.setValue(30);self.stops=QSpinBox();self.stops.setRange(0,3);self.stops.setValue(2);self.interval=QSpinBox();self.interval.setRange(1,1440);self.interval.setValue(2);self.interval.setSuffix(' min')
  for n,w in [('Origen',self.o),('Destino',self.d),('Salida',self.dep),('Regreso',self.ret),('Edad',self.age),('Max escalas',self.stops),('Intervalo',self.interval)]:f.addRow(n,w)
  buttons=QHBoxLayout()
  for text,fn in [('Iniciar agente',self.start),('Detener',self.agent.stop),('Diagnostico visible',self.visible),('Reproducir',self.replay)]:b=QPushButton(text);b.clicked.connect(fn);buttons.addWidget(b)
  w=QWidget();w.setLayout(buttons);f.addRow(w);g=QGroupBox('Objetivo de monitoreo');g.setLayout(f);root.addWidget(g)
  tabs=QTabWidget();root.addWidget(tabs,1)
  self.table=QTableWidget(0,9);self.table.setHorizontalHeaderLabels(['Fuente','Precio','Aerolinea','Origen','Destino','Ida','Vuelta','Escalas','Observado']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);tabs.addTab(self.table,'Ofertas actuales')
  intel=QWidget();iv=QVBoxLayout(intel);cards=QGridLayout();self.metrics={}
  for i,k in enumerate(['Actual','Minimo','P10','P25','Mediana','P75','Maximo','Ciclos','Dias','Clasificacion','Score','Confianza']):
   box=QGroupBox(k);v=QVBoxLayout(box);lab=QLabel('—');lab.setStyleSheet('font-size:17px;font-weight:600');v.addWidget(lab);cards.addWidget(box,i//6,i%6);self.metrics[k]=lab
  iv.addLayout(cards);self.reason=QLabel('Acumulando observaciones propias.');self.reason.setWordWrap(True);iv.addWidget(self.reason);self.chart=HistoryChart();iv.addWidget(self.chart);tabs.addTab(intel,'Inteligencia de compra')
  logs=QWidget();lv=QVBoxLayout(logs);self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(2000);lv.addWidget(self.log);self.learning_panel=LearningPanel(self.req,self);tabs.addTab(self.learning_panel,'Aprendizaje y reparación');tabs.addTab(logs,'Log del agente');self.log_add(datetime.now(),'Aplicacion iniciada. Providers: Almundo estable; Aerolineas Argentinas experimental y auditable.');self.refresh()
 def req(self):return SearchRequest(self.o.text().strip().upper(),self.d.text().strip().upper(),self.dep.date().toPyDate(),self.ret.date().toPyDate(),(self.age.value(),self.age.value()),max_stops=self.stops.value())
 def status_set(self,s):self.status.setText('● '+s);self.activity.setText(datetime.now().strftime('%H:%M:%S'))
 def log_add(self,t,m):self.log.appendPlainText(f'[{t:%d/%m/%Y %H:%M:%S}] {m}');self.activity.setText(m[:100])
 def start(self):
  if not self.agent.running:self.last=self.req();self.agent.start(self.last,self.interval.value())
 def visible(self):
  try:self.last=self.req();obs=AlmundoProvider().search(self.last,True);[database.insert(x) for x in obs];self.observed(obs)
  except Exception as e:QMessageBox.critical(self,'Diagnostico',str(e))
 def observed(self,obs):
  self.table.setRowCount(0)
  for o in obs[:30]:
   vals=[o.provider,f'{o.price:.0f}',o.airline,o.request.origin,o.request.destination,o.request.departure.strftime('%d/%m/%Y'),o.request.return_date.strftime('%d/%m/%Y'),str(o.stops if o.stops is not None else '?'),o.observed_at.strftime('%d/%m %H:%M')];r=self.table.rowCount();self.table.insertRow(r)
   for c,v in enumerate(vals):self.table.setItem(r,c,QTableWidgetItem(v))
  if obs:self.last=obs[0].request
  self.refresh()
 def refresh(self):
  r=self.last or self.req();a=database.analytics(r);s=signal(a,(r.departure-date.today()).days);vals={'Actual':f"USD {a['current']:.0f}" if a else '—','Minimo':f"USD {a['minimum']:.0f}" if a else '—','P10':f"USD {a['p10']:.0f}" if a else '—','P25':f"USD {a['p25']:.0f}" if a else '—','Mediana':f"USD {a['median']:.0f}" if a else '—','P75':f"USD {a['p75']:.0f}" if a else '—','Maximo':f"USD {a['maximum']:.0f}" if a else '—','Ciclos':str(a['count']) if a else '0','Dias':str(a['history_days']) if a else '0','Clasificacion':s['label'],'Score':f"{s['score']}/100",'Confianza':s['confidence']}
  for k,v in vals.items():self.metrics[k].setText(v)
  self.reason.setText(s['reason']+' La conversión ARS→USD usa una cotización oficial BCRA guardada una sola vez por día publicado. Los percentiles se calculan con el mejor precio de cada ciclo, no con todas las tarjetas de una misma consulta.');self.chart.render(a)
 def replay(self):
  r=self.last or self.req()
  row=self.table.currentRow()
  provider='almundo'
  if row>=0:
   item=self.table.item(row,0)
   if item and item.text().strip():provider=item.text().strip().lower()
  if provider not in ('almundo','aerolineas'):
   QMessageBox.warning(self,'Replay',f'Provider {provider} todavía no soporta Replay.');return
  profile_id=uuid.uuid4().hex
  cmd=[sys.executable,'-m','flight_watch.replay_process','--profile-id',profile_id,'--provider',provider,'--origin',r.origin,'--destination',r.destination,'--departure',r.departure.isoformat(),'--return-date',r.return_date.isoformat(),'--age',str(r.ages[0] if r.ages else 30),'--max-stops',str(r.max_stops)]
  try:
   log_dir=Path(__file__).resolve().parents[2]/'data'/'diagnostics'/'replay';log_dir.mkdir(parents=True,exist_ok=True);log_file=open(log_dir/f'{profile_id}.log','a');subprocess.Popen(cmd,cwd=str(Path(__file__).resolve().parents[2]),start_new_session=True,stdout=log_file,stderr=log_file)
   self.log_add(datetime.now(),f'Replay {provider} iniciado para la fila seleccionada.')
  except Exception as e:QMessageBox.critical(self,'Replay',str(e))
 def closeEvent(self,e):
  if hasattr(self,'learning_panel'):self.learning_panel.shutdown()
  if self.agent.running:self.agent.stop();self.agent.thread.join(timeout=5)
  e.accept()
def main():app=QApplication(sys.argv);w=Window();w.show();sys.exit(app.exec())
if __name__=='__main__':main()
