from __future__ import annotations
from datetime import datetime
import requests
from . import database
BCRA_URL='https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD'
RATE_TYPE='BCRA_USD_COTIZACION'

def latest_usd_rate(force=False):
    """Una cotización oficial USD/ARS por fecha publicada. Reusa SQLite y no consulta cada 2 minutos."""
    cached=database.latest_exchange_rate('USD',RATE_TYPE)
    if cached and not force:
        # La publicación puede corresponder al último día hábil. Durante el mismo día local, reutilizarla.
        fetched=datetime.fromisoformat(cached['retrieved_at'])
        if fetched.date()==datetime.now().date(): return cached
    r=requests.get(BCRA_URL,headers={'Accept':'application/json','User-Agent':'FlightWatchAgent/0.11.0'},timeout=30)
    r.raise_for_status();j=r.json();results=j.get('results') or []
    if not results: raise RuntimeError('BCRA no devolvió cotización USD')
    item=results[0];detail=next((x for x in item.get('detalle',[]) if x.get('codigoMoneda')=='USD'),None)
    if not detail: raise RuntimeError('BCRA no devolvió detalle USD')
    value=float(detail['tipoCotizacion']);rate_date=item['fecha']
    database.upsert_exchange_rate(rate_date,'USD',value,RATE_TYPE,'BCRA estadisticas cambiarias',datetime.now().isoformat())
    return database.exchange_rate(rate_date,'USD',RATE_TYPE)

def ars_to_usd(ars):
    rate=latest_usd_rate();return round(float(ars)/float(rate['ars_per_unit']),2),rate
