"""Collects vacancies from public career-site data sources into data/vacancies.json.
Runs daily in GitHub Actions. Each source is isolated: a failing source never breaks the others."""
import json, os, re, ssl, time, sys, urllib.request, urllib.error, urllib.parse, datetime, traceback, asyncio
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
NOVERIFY=ssl.create_default_context(); NOVERIFY.check_hostname=False; NOVERIFY.verify_mode=ssl.CERT_NONE
RU_CA_HOSTS=("tbank.ru","alfabank.ru","tochka.com","vtb.ru","sovcombank.ru","ptsecurity.com")
def http(url,data=None,headers=None,timeout=30):
    h={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Accept-Language":"ru-RU,ru;q=0.9"}
    if headers: h.update(headers)
    body=None
    if data is not None:
        body=json.dumps(data).encode(); h["Content-Type"]="application/json"
    req=urllib.request.Request(url,data=body,headers=h)
    ctx=NOVERIFY if any(x in url for x in RU_CA_HOSTS) else None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=timeout,context=ctx) as r: return r.read().decode("utf8","replace"), r.status, r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<2: time.sleep(3*(attempt+1)); continue
            raise
        except Exception:
            if attempt<2: time.sleep(3); continue
            raise
def jget(url,**kw): return json.loads(http(url,**kw)[0])
def clean(s): return re.sub(r"\s+"," ",(s or "").replace("\xa0"," ")).strip()
def fmt_norm(*vals):
    t=" ".join(clean(str(v)).lower() for v in vals if v)
    out=[]
    if re.search(r"удал|remote",t): out.append("remote")
    if re.search(r"гибр|hybrid|комбинир|mixed|гибк",t): out.append("hybrid")
    if re.search(r"офис|office|на месте",t): out.append("office")
    return out
def V(title,url,city="",fmt=None,area="",date=""):
    return {"t":clean(title),"u":url,"c":clean(city).replace("г ","",1) if clean(city).startswith("г ") else clean(city),"f":fmt or [],"a":clean(area),"d":(date or "")[:10]}

# ---------- JSON sources ----------
PAGING={}
def paged(name,schemes,extract,idf,maxpages=150,pause=.3):
    """Try URL schemes until one where page 2 differs from page 1, then walk pages until no new ids."""
    for si,(start,mk) in enumerate(schemes):
        try:
            a=extract(jget(mk(start))); b=extract(jget(mk(start+1)))
        except Exception as e:
            continue
        if not a: continue
        ida={idf(x) for x in a}; idb={idf(x) for x in b}
        if not b or idb<=ida:
            if si==len(schemes)-1: PAGING[name]=f"single page (scheme {si})"; return a
            continue
        PAGING[name]=f"scheme {si}"
        out=a+b; seen=ida|idb; p=start+2
        while p<start+maxpages:
            items=extract(jget(mk(p))); new=[x for x in items if idf(x) not in seen]
            if not new: break
            seen|={idf(x) for x in new}; out+=new; p+=1; time.sleep(pause)
        return out
    PAGING[name]="no scheme worked"; return []

def yandex():
    out=[]; url="https://yandex.ru/jobs/api/publications/?page_size=100"
    for _ in range(40):
        d=jget(url)
        for r in d["results"]:
            v=r.get("vacancy") or {}
            out.append(V(r["title"],f"https://yandex.ru/jobs/vacancies/{r['publication_slug_url']}",
              ", ".join(c["name"] for c in v.get("cities",[])[:3]),fmt_norm(*[m["name"] for m in v.get("work_modes",[])]),
              (r.get("public_service") or {}).get("name",""),r.get("modified","")))
        nxt=d.get("next")
        if not nxt: break
        q=urllib.parse.urlparse(nxt).query; url="https://yandex.ru/jobs/api/publications/?"+q; time.sleep(.5)
    return out
def sber():
    B="https://rabota.sber.ru/public/app-candidate-public-api-gateway/api/v1/publications"
    items=paged("sber",[(0,lambda p:f"{B}?page={p}&size=100"),(1,lambda p:f"{B}?page={p}&size=100"),(0,lambda p:f"{B}?pageNumber={p}&pageSize=100"),
        (0,lambda p:f"{B}?offset={p*100}&limit=100"),(0,lambda p:f"{B}?from={p*100}&size=100"),(0,lambda p:f"{B}?page={p}"),(1,lambda p:f"{B}?page={p}")],
        lambda d:(d.get("data") or {}).get("vacancies") or [], lambda r:r["internalId"])
    return [V(r["title"],f"https://rabota.sber.ru/search/{r['internalId']}",r.get("city") or r.get("region"),[],(r.get("specialization") or "").split(":")[-1],r.get("publicationDate","")) for r in items]
def vk():
    out=[]; url="https://team.vk.company/career/api/v2/vacancies/?limit=100&offset=0"
    while url:
        d=jget(url.replace("http://","https://"))
        for r in d["results"]:
            f=fmt_norm(r.get("work_format"))
            if r.get("remote") and "remote" not in f: f.append("remote")
            out.append(V(r["title"],f"https://team.vk.company/vacancy/{r['id']}/",(r.get("town") or {}).get("name",""),f,
              " · ".join(x for x in [(r.get("group") or {}).get("name",""),(r.get("specialty") or {}).get("name","")] if x)))
        url=d.get("next"); time.sleep(.4)
    return out
def ozon():
    B="https://job-api.ozon.ru/v2/vacancy"
    items=paged("ozon",[(1,lambda p:f"{B}?page={p}&perPage=100"),(1,lambda p:f"{B}?page={p}&limit=100"),(1,lambda p:f"{B}?pageNumber={p}&perPage=100"),(0,lambda p:f"{B}?offset={p*100}&limit=100"),(1,lambda p:f"{B}?page={p}")],
        lambda d:d.get("items") or [], lambda r:r["hhId"],maxpages=200)
    return [V(r["title"],r.get("externalLink") or f"https://career.ozon.ru/vacancy/{r['hhId']}/",r.get("city"),fmt_norm(*(r.get("workFormat") or [])),r.get("department","")) for r in items]
def mts():
    B="https://job.mts.ru/api/v2/vacancies"
    items=paged("mts",[(1,lambda p:f"{B}?pagination[page]={p}&pagination[pageSize]=100"),(1,lambda p:f"{B}?page={p}&pageSize=100"),(1,lambda p:f"{B}?page={p}&limit=100"),(0,lambda p:f"{B}?page={p}&size=100"),(1,lambda p:f"{B}?page={p}")],
        lambda d:d.get("data") or [], lambda r:r["slug"],maxpages=200)
    return [V(r["title"],f"https://job.mts.ru/vacancy/{r['slug']}",(r.get("region") or {}).get("title",""),fmt_norm(*[w.get("title") for w in (r.get("workFormats") or [])]),", ".join(c.get("title","") for c in (r.get("categories") or [])[:1]),r.get("publishedAt","")) for r in items]
def tbank():
    out=[]; offset=0; cats={"tcareer_it":"it","tcareer_back_office":"back-office","tcareer_work_with_clients":"service"}
    names={"tcareer_it":"ИТ","tcareer_back_office":"Офис","tcareer_work_with_clients":"Работа с клиентами"}
    while offset<3000:
        body={"filters":{"generatedGraphQL":{"type":"T_CAREER","status":"ACTIVE","searchFiasIds":[],"includeSeoAndPcPublications":False,"includeInternshipPublications":True,
              "userGroup":{"groups":["Control"],"type":"SPECIFIC"},"collapsePredstavitelPublications":True,
              "or":[{"category":c} for c in cats]}},"pagination":{"offset":offset,"isFinished":False}}
        d=jget("https://www.tbank.ru/pfpjobs/papi/getVacancies",data=body)
        items=(d.get("payload") or {}).get("vacancies") or []
        for r in items:
            seg=cats.get(r.get("category"),"it"); slug=r.get("seoSlug") or "vacancy"
            url=f"https://www.tbank.ru/career/{seg}/vacancy/moscow/{slug}/{r['urlSlug']}/"
            out.append(V(r["title"],url,r.get("subtitle") or "",fmt_norm(*(r.get("tags") or [])),names.get(r.get("category"),"")))
        if len(items)<1: break
        offset+=len(items); time.sleep(.5)
    return out
def alfa():
    out=[]; skip=0
    while skip<5000:
        d=jget(f"https://job.alfabank.ru/api/vacancies?take=100&skip={skip}")
        items=d.get("items") or []
        for r in items:
            slug=re.sub(r"[^a-z0-9]+","-",r.get("code","") or "").strip("-") or "vacancy"
            out.append(V(r["name"],f"https://job.alfabank.ru/vacancies/moskva/central-office/vacancy_{r['id']}",""))
        skip+=len(items)
        if not items or skip>=d.get("total",0): break
        time.sleep(.4)
    return out
def tochka():
    out=[]; page=1
    while page<30:
        d=jget(f"https://hr.tochka.com/data/v2/hr/vacancies/list.json?page={page}")
        for r in d["items"]:
            out.append(V(r["title"],(r["customLink"].get("url") if isinstance(r.get("customLink"),dict) and r["customLink"].get("url") else (r["customLink"] if isinstance(r.get("customLink"),str) and r.get("customLink") else f"https://hr.tochka.com/vacancies/catalog/{r['slug']}/")),(r.get("city") or {}).get("title","") if isinstance(r.get("city"),dict) else (r.get("city") or ""),
              ["remote"] if r.get("workFormat")=="remotely" else fmt_norm(r.get("workFormat")),(r.get("mainCategory") or {}).get("title","")))
        m=d["meta"]
        if page*m["pageSize"]>=m["total"]: break
        page+=1; time.sleep(.4)
    return out
def rwb():
    out=[]; offset=0
    while offset<5000:
        d=jget(f"https://career.rwb.ru/hr-crm-api/api/v2/pub/vacancies?limit=100&offset={offset}")["data"]
        items=d.get("items") or []
        for r in items:
            out.append(V(r["name"],f"https://career.rwb.ru/vacancies/{r['id']}",r.get("city_title"),fmt_norm(*[e["title"] for e in r.get("employment_types",[])]),r.get("direction_title","")))
        offset+=len(items)
        if not items: break
        time.sleep(.4)
    return out
def x5():
    out=[]; page=1
    while page<200:
        d=jget(f"https://rabota.x5.ru/vacancy/api/v1/public/vacancies?page={page}&page_size=100")
        items=d.get("items") or []
        for r in items:
            bu=", ".join(b["business_unit"]["name"] for b in r.get("business_units",[])[:1])
            cat=(r.get("category") or {}); area=" · ".join(x for x in [bu,(cat.get("parent") or {}).get("name") or cat.get("name","")] if x)
            out.append(V(r["name"],f"https://rabota.x5.ru/vacancies/{r['id']}",r.get("city"),fmt_norm(r.get("work_format")),area,r.get("published_at","")))
        if len(items)<100: break
        page+=1; time.sleep(.3)
    return out
def lamoda():
    out=[]; start=0
    while start<3000:
        d=jget(f"https://job.lamoda.ru/api/hr/vacancies/compact?search=&minExperience=&pagination[start]={start}&pagination[limit]=100")
        items=d.get("data") or []
        for r in items:
            out.append(V(r["name"],f"https://job.lamoda.ru/vacancies/{r['slug']}",(r.get("location") or {}).get("name",""),[],(r.get("department") or {}).get("name",""),r.get("externalPublicationDate","")))
        start+=len(items)
        if len(items)<100: break
        time.sleep(.3)
    return out
def lanit():
    d=jget("https://job.lanit.ru/_vti_bin/Lanit.Job.Redesign/WebService.svc/GetVacancyForWidget")
    return [V(r["Title"],r["Url"],r.get("City") or "") for r in d]

# ---------- rendered-page sources (headless browser) ----------
RENDER={
 "avito":{"pages":"https://career.avito.com/vacancies/?PAGEN_1={p}","url":"https://career.avito.com/vacancies/","re":r"^/vacancies/[a-z0-9\-]+/\d+/$","base":"https://career.avito.com"},
 "kaspersky":{"pages":"https://careers.kaspersky.ru/vacancies?page={p}","url":"https://careers.kaspersky.ru/vacancies","re":r"^/vacancy/\d+$","base":"https://careers.kaspersky.ru"},
 "gis":{"url":"https://job.2gis.ru/vacancies","re":r"^/vacancies/[a-z_]+/\d+$","base":"https://job.2gis.ru"},
 "megafon":{"pages":"https://job.megafon.ru/vacancy/all/any?page={p}","url":"https://job.megafon.ru/vacancy/all/any","re":r"^/vacancy/[a-z\-]+/[a-z\-]+/.+-\d+$","base":"https://job.megafon.ru"},
 "kontur":{"pages":"https://kontur.ru/career/vacancies?page={p}","url":"https://kontur.ru/career/vacancies","re":r"^/career/vacancies/\d+$","base":"https://kontur.ru"},
}
MORE_JS="""() => { const b=[...document.querySelectorAll('button,a,div[role=button]')].find(e=>/показать ещё|показать еще|загрузить ещё|загрузить еще|ещё вакансии|больше вакансий/i.test((e.innerText||'').trim()) && e.offsetParent!==null); if(b){b.click();return true} return false }"""
def parse_render(key,href,text):
    lines=[clean(x) for x in (text or "").split("\n") if clean(x)]
    if not lines: return None
    city=""; title=lines[0]; area=""
    if key=="gis":
        if "Откликнуться" in lines:
            i=lines.index("Откликнуться"); city=lines[i-1] if i>0 else ""; title=lines[i+1] if i+1<len(lines) else title; area=lines[0]
    elif key=="megafon":
        if len(lines)>=3: city,area,title=lines[0],lines[1],lines[2]
    elif key=="kontur":
        m=re.match(r"(.+?)\s{2,}(.+)",(text or "").replace("\xa0"," "))
        title=lines[0]
    return title,city,area
async def render_all(results,meta):
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        for k in RENDER: meta[k]={"ok":False,"error":"playwright missing"}
        return
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for key,cfg in RENDER.items():
            t0=time.time()
            try:
                ctx=await b.new_context(ignore_https_errors=True,locale="ru-RU",user_agent=UA); page=await ctx.new_page()
                await page.goto(cfg["url"],timeout=60000,wait_until="domcontentloaded"); await page.wait_for_timeout(3000)
                last=0
                for _ in range(60):
                    await page.mouse.wheel(0,6000); await page.wait_for_timeout(700)
                    clicked=await page.evaluate(MORE_JS)
                    n=await page.eval_on_selector_all("a[href]","els=>els.length")
                    if not clicked and n==last: break
                    last=n; await page.wait_for_timeout(900 if clicked else 300)
                links=await page.eval_on_selector_all("a[href]","els=>els.map(e=>[e.getAttribute('href'),e.innerText||''])")
                rx=re.compile(cfg["re"])
                if cfg.get("pages"):
                    known={l[0] for l in links if rx.match(l[0].replace(cfg["base"],""))}
                    for pn in range(2,40):
                        await page.goto(cfg["pages"].format(p=pn),timeout=60000,wait_until="domcontentloaded"); await page.wait_for_timeout(1800)
                        more=await page.eval_on_selector_all("a[href]","els=>els.map(e=>[e.getAttribute('href'),e.innerText||''])")
                        new=[l for l in more if rx.match(l[0].replace(cfg["base"],"")) and l[0] not in known]
                        if not new: break
                        known|={l[0] for l in new}; links+=new
                seen={}
                for href,text in links:
                    h=href.replace(cfg["base"],"")
                    if not rx.match(h): continue
                    p_=parse_render(key,h,text)
                    if p_ and (h not in seen or len(p_[0])>len(seen[h][0])): seen[h]=p_
                vs=[V(t,cfg["base"]+h,"" if re.match(r"удал",c,re.I) else c,(["remote"] if re.match(r"удал",c,re.I) else fmt_norm(t)),a) for h,(t,c,a) in seen.items() if t and len(t)>2]
                results[key]=vs; meta[key]={"ok":True,"n":len(vs),"sec":round(time.time()-t0,1),"mode":"render"}
                await ctx.close()
            except Exception as e:
                meta[key]={"ok":False,"error":repr(e)[:300]}
            print(key,meta[key],flush=True)
        await b.close()

SOURCES={"yandex":yandex,"sber":sber,"vk":vk,"ozon":ozon,"mts":mts,"tbank":tbank,"alfa":alfa,"tochka":tochka,"rwb":rwb,"x5":x5,"lamoda":lamoda,"lanit":lanit}
def main():
    only=sys.argv[1:] or None
    os.makedirs("data",exist_ok=True)
    prev={}
    try: prev=json.load(open("data/vacancies.json",encoding="utf8"))["sources"]
    except Exception: pass
    results={}; meta={}
    for k,fn in SOURCES.items():
        if only and k not in only: continue
        t0=time.time()
        try:
            vs=fn(); 
            seen=set(); vs=[v for v in vs if v["t"] and not (v["u"] in seen or seen.add(v["u"]))]
            results[k]=vs; meta[k]={"ok":True,"n":len(vs),"sec":round(time.time()-t0,1)}
        except Exception as e:
            meta[k]={"ok":False,"error":repr(e)[:300]}; traceback.print_exc()
        print(k,meta[k],flush=True)
    if not only or any(k in RENDER for k in only):
        asyncio.run(render_all(results,meta))
    # sample-link check
    for k,vs in results.items():
        if not vs: continue
        try:
            _,st,final=http(vs[0]["u"],headers={"Accept":"text/html"},timeout=25); meta[k]["link"]=st; meta[k]["final"]=final[:200]
        except urllib.error.HTTPError as e: meta[k]["link"]=e.code
        except Exception as e: meta[k]["link"]=repr(e)[:80]
    # keep previous data for failed sources (stale but useful), mark it
    for k,old in prev.items():
        if k not in results and old.get("v"):
            results[k]=old["v"]; meta.setdefault(k,{})["stale_from"]=old.get("at")
    now=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    out={"updated":now,"sources":{k:{"at":(prev.get(k,{}).get("at") if meta.get(k,{}).get("stale_from") else now),"v":v} for k,v in results.items()}}
    json.dump(out,open("data/vacancies.json","w",encoding="utf8"),ensure_ascii=False,separators=(",",":"))
    json.dump({"updated":now,"paging":PAGING,"sources":meta},open("data/meta.json","w",encoding="utf8"),ensure_ascii=False,indent=1)
    print("TOTAL",sum(len(v) for v in results.values()))
if __name__=="__main__": main()
