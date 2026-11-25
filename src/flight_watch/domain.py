from dataclasses import dataclass,asdict
from datetime import date,datetime
import json
@dataclass(frozen=True)
class SearchRequest:
 origin:str;destination:str;departure:date;return_date:date;ages:tuple[int,...]=(30,);cabin:str="ECONOMY";max_stops:int=2
 def counts(self):return sum(a>=18 for a in self.ages),sum(2<=a<18 for a in self.ages),sum(a<2 for a in self.ages)
 def to_json(self):
  d=asdict(self);d["departure"]=self.departure.isoformat();d["return_date"]=self.return_date.isoformat();d["ages"]=list(self.ages);return json.dumps(d)
@dataclass
class Observation:
 provider:str;request:SearchRequest;price:float;currency:str;observed_at:datetime;url:str="";airline:str="";stops:int|None=None;details:str="";batch_id:str=""
