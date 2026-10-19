import asyncio, json, os
from playwright.async_api import async_playwright
SITES={
 "tbank":"https://www.tbank.ru/career/vacancies/",
 "alfa":"https://digital.alfabank.ru/vacancies",
 "vtb":"https://rabota.vtb.ru/vacancies/",
 "sovcom":"https://people.sovcombank.ru/vacancies",
 "tochka":"https://hr.tochka.com/vacancies/",
 "pt":"https://ptsecurity.com/about/vacancy/",
 "gpb":"https://www.gazprombank.ru/vacancy/",
 "rt":"https://job.rt.ru/vacancies",
 "rwb":"https://career.rwb.ru/vacancies",
 "samokat":"https://samokat.tech/vacancies",
 "cian":"https://www.cian.ru/vacancies/",
 "x5":"https://rabota.x5.ru/vacancies?vacancy_categories=it",
 "lamoda":"https://job.lamoda.ru/vacancies",
 "avito":"https://career.avito.com/vacancies/",
 "kontur":"https://kontur.ru/career/vacancies",
 "gis":"https://job.2gis.ru/vacancies",
 "selectel":"https://selectel.ru/careers/all/",
 "megafon":"https://job.megafon.ru/vacancy/all/any",
 "kaspersky":"https://careers.kaspersky.ru/vacancies",
 "astra":"https://astra.ru/about/career/vacancies/",
 "softline":"https://softline.ru/about/vacancies",
 "beeline":"https://job.beeline.ru/job-specialists/all/",
 "lanit":"https://job.lanit.ru/",
}
async def run():
    os.makedirs("probe2",exist_ok=True); summary={}
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for k,u in SITES.items():
            ctx=await b.new_context(ignore_https_errors=True,locale="ru-RU",user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
            page=await ctx.new_page(); caps=[]
            async def on_resp(r):
                try:
                    ct=r.headers.get("content-type","")
                    if "json" in ct and r.request.resource_type in ("xhr","fetch"):
                        body=await r.text()
                        caps.append({"url":r.url,"method":r.request.method,"post":(r.request.post_data or "")[:600],"status":r.status,"len":len(body),"head":body[:1500]})
                except Exception as e: pass
            page.on("response",on_resp)
            info={"url":u}
            try:
                resp=await page.goto(u,timeout=45000,wait_until="domcontentloaded")
                info["status"]=resp.status if resp else None
                for _ in range(4):
                    await page.wait_for_timeout(2000); await page.mouse.wheel(0,4000)
                html=await page.content(); info["html_len"]=len(html)
                links=await page.eval_on_selector_all("a[href]","els=>els.map(e=>[e.getAttribute('href'),(e.innerText||'').trim().slice(0,120)])")
                vl=[l for l in links if l[0] and ("vacanc" in l[0] or "/vacancy" in l[0] or "/job" in l[0])]
                info["n_links"]=len(vl); info["links"]=vl[:40]
                open(f"probe2/{k}.html","w",encoding="utf8").write(html[:400000])
            except Exception as e:
                info["error"]=repr(e)[:300]
            caps.sort(key=lambda c:-c["len"]); info["json"]=caps[:12]
            summary[k]=info; print(k,info.get("status"),info.get("n_links"),len(caps),info.get("error","")[:80],flush=True)
            await ctx.close()
        await b.close()
    json.dump(summary,open("probe2/summary.json","w",encoding="utf8"),ensure_ascii=False,indent=1)
asyncio.run(run())
