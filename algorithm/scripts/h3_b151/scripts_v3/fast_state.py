"""聚合状态；正式模式不存逐SMALL记录。"""
from collections import Counter
class State:
 def __init__(self):
  self.early=False;self.mode='LEGACY_FULL';self.counts=Counter();self.ids=None;self.core=None;self.window=None;self.params={}
 def geometry(self,core,window):self.core=core;self.window=window
 def count(self,key,n=1):self.counts[key]+=int(n)
STATE=State()
