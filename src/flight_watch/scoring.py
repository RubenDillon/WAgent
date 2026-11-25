def signal(a,days):
 if not a:return {'label':'SIN DATOS','score':0,'confidence':'NULA','reason':'Sin observaciones propias.'}
 n,span=a['count'],a['history_days'];cur=a['current']
 if n<5 or span<2:return {'label':'APRENDIENDO','score':20,'confidence':'BAJA','reason':f'{n} ciclos en {span} dia(s). Acumulando historial propio.'}
 p10,p25,med,p75=a['p10'],a['p25'],a['median'],a['p75']
 if cur<=p10:label='EXCEPCIONAL';base=90
 elif cur<=p25:label='MUY BUENO';base=78
 elif cur<=med:label='BUENO';base=65
 elif cur<=p75:label='NORMAL';base=45
 else:label='ALTO';base=25
 horizon=5 if 30<=days<=210 else 0;coverage=min(5,n//5);score=min(100,base+horizon+coverage);conf='ALTA' if n>=15 and span>=7 else 'MEDIA'
 return {'label':label,'score':score,'confidence':conf,'reason':f'Actual USD {cur:.0f}; P10 {p10:.0f}; P25 {p25:.0f}; mediana {med:.0f}; P75 {p75:.0f}. Faltan {days} dias.'}
