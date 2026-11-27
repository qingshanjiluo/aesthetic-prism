# 最小探针：直接对已加载的 8004 page 执行 evaluate
import json, urllib.request
import websocket

d = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
pg = next(t for t in d if t.get("type") == "page" and "8005" in (t.get("url") or ""))
c = websocket.create_connection(pg["webSocketDebuggerUrl"], timeout=30)
mid = [0]

def cmd(method, **p):
    mid[0] += 1
    c.send(json.dumps({"id": mid[0], "method": method, "params": p}))
    while True:
        m = json.loads(c.recv())
        if m.get("id") == mid[0]:
            return m.get("result", m)

cmd("Runtime.enable")
cmd("Page.enable")
cmd("Page.reload", ignoreCache=True)
import time as _t
for _ in range(40):
    r = cmd("Runtime.evaluate", expression="document.readyState")
    if r.get("result", {}).get("value") == "complete":
        break
    _t.sleep(0.3)
cmd("Runtime.evaluate", expression="document.getElementById('login-view').hidden=true;")
import time as _t2
_t2.sleep(0.5)
r = cmd("Runtime.evaluate", expression="""(function(){
  var out={};
  out.tabs=Array.from(document.querySelectorAll('#app-tabs .tab')).map(t=>t.dataset.view);
  document.querySelector('#app-tabs .tab[data-view="annotate"]').click();
  out.after=Array.from(document.querySelectorAll('[id^=view-]')).map(el=>el.id+'='+el.hidden).join(' | ');
  out.annotDisp=getComputedStyle(document.getElementById('view-annotate')).display;
  out.annotTop=document.getElementById('view-annotate').getBoundingClientRect().top;
  out.annotH=document.getElementById('view-annotate').getBoundingClientRect().height;
  out.homeDisp=getComputedStyle(document.getElementById('view-home')).display;
  out.homeHidden=document.getElementById('view-home').hidden;
  out.active=document.querySelector('#app-tabs .tab.active').dataset.view;
  out.scrollY=window.scrollY;
  out.scrollH=document.documentElement.scrollHeight;
  return JSON.stringify(out);
})()""")
print(r.get("result", {}).get("value"))
c.close()
