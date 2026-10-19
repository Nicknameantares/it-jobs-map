import asyncio, json, os
from playwright.async_api import async_playwright
SITES={"sber":"https://rabota.sber.ru/search/","ozon":"https://career.ozon.ru/vacancy/","tochka":"https://hr.tochka.com/vacancies/","avito":"https://career.avito.com/vacancies/","kontur":"https://kontur.ru/career/vacancies"}
MORE="""() => { const b=[...document.querySelectorAll('button,a,div[role=button],span')].filter(e=>/показать ещё|показать еще|загрузить ещё|ещё вакансии|следующая|далее|^2$/i.test((e.innerText||'').trim()) && e.offsetParent!==null); if(b.length){b[0].click();return (b[0].innerText||'').trim()} return null }"""
async def run():
    os.makedirs("probe3",exist_ok=True); out={}
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for k,u in SITES.items():
            ctx=await b.new_context(ignore_https_errors=True,locale="ru-RU",user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
            page=await ctx.new_page(); reqs=[]
            page.on("request",lambda r: reqs.append({"url":r.url,"m":r.method,"post":(r.post_data or "")[:800]}) if r.resource_type in ("xhr","fetch") else None)
            info={"url":u}
            try:
                r=await page.goto(u,timeout=60000,wait_until="domcontentloaded"); info["status"]=r.status if r else None; info["final"]=page.url
                await page.wait_for_timeout(4000); info["clicks"]=[]
                for _ in range(4):
                    await page.mouse.wheel(0,8000); await page.wait_for_timeout(1500)
                    c=await page.evaluate(MORE); info["clicks"].append(c); await page.wait_for_timeout(2500)
            except Exception as e: info["error"]=repr(e)[:300]
            info["reqs"]=[x for x in reqs if not any(s in x["url"] for s in ("yandex","mindbox","google","sentry","uxfeedback","top-fwz","vk.com/rtrg","mc.","metrika"))][:60]
            out[k]=info; print(k,info.get("status"),info.get("clicks"),len(info["reqs"]),flush=True)
            await ctx.close()
        await b.close()
    json.dump(out,open("probe3/summary.json","w",encoding="utf8"),ensure_ascii=False,indent=1)
asyncio.run(run())
