import json, re, sys, time, urllib.request, urllib.error, ssl, os
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
URLS=[l.strip() for l in open("tools/probe_urls.txt",encoding="utf8") if l.strip() and not l.startswith("#")]
os.makedirs("probe",exist_ok=True)
out=[]
for i,u in enumerate(URLS):
    rec={"url":u}
    try:
        req=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"text/html,application/json;q=0.9,*/*;q=0.8","Accept-Language":"ru-RU,ru;q=0.9"})
        with urllib.request.urlopen(req,timeout=25) as r:
            b=r.read(3_000_000); rec["status"]=r.status; rec["ctype"]=r.headers.get("content-type"); rec["final"]=r.geturl()
    except urllib.error.HTTPError as e:
        rec["status"]=e.code; b=e.read(200000) if hasattr(e,"read") else b""
    except Exception as e:
        rec["error"]=repr(e)[:200]; b=b""
    t=b.decode("utf8","replace")
    rec["len"]=len(t)
    rec["next_data"]="__NEXT_DATA__" in t; rec["nuxt"]="__NUXT__" in t or "window.__NUXT" in t
    rec["api_urls"]=sorted(set(re.findall(r'["\'](/[a-zA-Z0-9_\-/]*api[a-zA-Z0-9_\-/]*)["\'?]',t)))[:40]
    rec["abs_api"]=sorted(set(re.findall(r'https?://[a-zA-Z0-9.\-]+/[a-zA-Z0-9_\-/.]*api[a-zA-Z0-9_\-/.]*',t)))[:40]
    rec["vac_links"]=sorted(set(re.findall(r'href="([^"]*vacanc[^"]*)"',t)))[:25]
    out.append(rec)
    fn=f"probe/{i:02d}.txt"
    open(fn,"w",encoding="utf8").write(u+"\n\n"+t[:60000])
    print(i,u,rec.get("status"),rec.get("len"),rec.get("error",""),flush=True)
    time.sleep(1)
json.dump(out,open("probe/summary.json","w",encoding="utf8"),ensure_ascii=False,indent=1)
