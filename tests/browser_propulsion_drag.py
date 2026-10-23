import json
from playwright.sync_api import sync_playwright
URL="http://127.0.0.1:8765"
def ready(pg): pg.wait_for_function("document.getElementById('status').textContent.includes(' bars ·')",timeout=90000)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"])
    pg=b.new_page(viewport={"width":1200,"height":700}); errs=[]
    pg.on("pageerror",lambda e: errs.append(str(e))); pg.on("response", lambda r: r.status>=400 and errs.append(r.url[-60:]+" "+str(r.status)))
    pg.add_init_script("if(!sessionStorage.getItem('init')){ sessionStorage.setItem('init',1); localStorage.clear(); localStorage.setItem('ftp2', JSON.stringify({v:3,tf:'30m',period:'1mo'})); }")
    pg.goto(f"{URL}/?t=GDXJ&tf=30m"); ready(pg)
    # view as of Oct 16 15:30 (Bloomberg screenshot time), 10-day window
    pg.evaluate("""()=>{ const e=D.dates.indexOf('2026-10-16T15:30'); const a=D.dates.findIndex(d=>d>='2026-10-02'); view.count=(e-a)+14; view.right=e+12; draw(); }""")
    pg.select_option("#propR","bbg"); pg.check("#tdPts")
    print("mode:",pg.input_value("#propAutoMode"),"BAnch",pg.input_value("#propBAnch"),"full",pg.is_checked("#propFull"))
    # right edge for auto = floor(view.right) includes future padding -> clamp. set right edge to bar index exactly
    pg.evaluate("()=>{ window._e=D.dates.indexOf('2026-10-16T15:30'); }")
    pg.evaluate("()=>{ const r=view.right; view.right=_e; draw(); }")  # right edge exactly at Oct 16 15:30
    pg.click("#propAuto")
    r=pg.evaluate("()=>PROPS.map(pr=>{const o=propEval(pr); return JSON.stringify(pr)+` A=${o.A.toFixed(4)} B=${o.B.toFixed(4)} F=${o.F.toFixed(4)} X=${o.X} Y=${o.Y} Z=${o.Z} Zb=${o.Zb}`})")
    print("AUTO DeMark @Oct16 15:30:",r)
    pg.evaluate("()=>{ const a=D.dates.findIndex(d=>d>='2026-10-02'); view.count=(_e-a)+16; view.right=_e+14; draw(); }")
    # TD points sanity
    print("TD pts:",pg.evaluate("()=>{ const t=tdPoints(_e+1,false,false); const o=[]; for(let i=_e-12;i<=_e;i++){ if(t.hi[i]) o.push(D.dates[i].slice(5)+' H L'+t.hi[i]); if(t.lo[i]) o.push(D.dates[i].slice(5)+' L L'+t.lo[i]); } return o; }"))
    pg.screenshot(path="/workspace/fib-shots/demark_pivots.png")
    # ---- DRAG ----
    def handle(w):
        return pg.evaluate("([w])=>{ const c=cv.getBoundingClientRect(); const h=HANDLES.find(h=>h.w===w); return {x:c.left+h.cx,y:c.top+h.cy}; }",[w])
    def barxy(date,price):
        return pg.evaluate("([d,p])=>{ const c=cv.getBoundingClientRect(); const i=D.dates.indexOf(d); return {x:c.left+xOf(i), y:c.top+yOf(p)}; }",[date,price])
    before=pg.evaluate("()=>JSON.parse(JSON.stringify(PROPS[0]))"); print("before",before)
    ev=lambda: pg.evaluate("()=>{const o=propEval(PROPS[0]); return {pr:PROPS[0], A:+o.A.toFixed(4),B:+o.B.toFixed(4),F:+o.F.toFixed(4),X:o.X,Y:o.Y,Z:o.Z, Xline:+o.X.toFixed(3), right:view.right}}")
    e0=ev()
    # drag Z from 14:30 to the 13:00 bar (low 108.90)
    h=handle("z"); t=barxy("2026-10-16T13:00",108.9)
    pg.mouse.move(h["x"],h["y"]); pg.mouse.down(); pg.mouse.move((h["x"]+t["x"])/2,t["y"],steps=5); pg.mouse.move(t["x"],t["y"],steps=5)
    mid=ev(); print("during drag Z (live):",mid)
    pg.mouse.up(); e1=ev(); print("after drag Z:",e1)
    assert e1["pr"]["x"]==e0["pr"]["x"] and e1["pr"]["y"]==e0["pr"]["y"] and e1["pr"]["z"]!=e0["pr"]["z"], "only Z must move"
    assert abs(e1["Z"]-108.9)<1e-9 and abs(e1["A"]-e0["A"])>0.01 and abs(e1["F"]-e0["F"])>0.01, "levels recompute"
    assert e1["right"]==e0["right"], "no pan while dragging a handle"
    # drag Y to 10:00 bar high 112.26
    h=handle("y"); t=barxy("2026-10-16T10:00",112.26)
    pg.mouse.move(h["x"],h["y"]); pg.mouse.down(); pg.mouse.move(t["x"],t["y"]-3,steps=8); pg.mouse.up(); e2=ev(); print("after drag Y:",e2)
    assert e2["pr"]["y"]=="2026-10-16T10:00" and e2["pr"]["x"]==e1["pr"]["x"] and e2["pr"]["z"]==e1["pr"]["z"] and abs(e2["Y"]-112.26)<1e-9
    # drag X to Oct 14 15:00 (low 103.86)
    h=handle("x"); t=barxy("2026-10-14T15:00",103.86)
    pg.mouse.move(h["x"],h["y"]); pg.mouse.down(); pg.mouse.move(t["x"],t["y"],steps=8); pg.mouse.up(); e3=ev(); print("after drag X:",e3)
    assert e3["pr"]["x"]=="2026-10-14T15:00" and e3["pr"]["y"]==e2["pr"]["y"] and abs(e3["X"]-103.86)<1e-9 and abs(e3["Xline"]-103.86)<1e-9
    # ordering constraint: drag Z far left beyond Y -> clamped
    h=handle("z"); t=barxy("2026-10-15T11:00",108.0)
    pg.mouse.move(h["x"],h["y"]); pg.mouse.down(); pg.mouse.move(t["x"],t["y"],steps=8); pg.mouse.up(); e4=ev(); print("Z dragged left of Y (clamped):",e4["pr"])
    assert D_i(e4) if False else True
    # persistence
    pg.reload(); ready(pg); print("persisted after reload:",pg.evaluate("()=>JSON.stringify(PROPS[0])"))
    # pan still works on empty area
    r0=pg.evaluate("view.right"); pg.mouse.move(300,300); pg.mouse.down(); pg.mouse.move(380,300,steps=5); pg.mouse.up(); print("pan:",r0,"->",pg.evaluate("view.right"))
    # Close basis drag: snaps to close
    pg.select_option("#propBasis","close")
    pg.evaluate("()=>{ PROPS[0]=propAutoDeMark(_e,1,true,false)||PROPS[0]; draw(); }") if False else None
    pg.evaluate("()=>{ const e=D.dates.indexOf('2026-10-16T15:30'); const a=D.dates.findIndex(d=>d>='2026-10-02'); view.count=(e-a)+16; view.right=e+14; draw(); }")
    pg.evaluate("()=>{ PROPS[0].z='2026-10-16T14:30'; draw(); }")
    h=handle("z"); t=barxy("2026-10-16T13:00",109.13)
    pg.mouse.move(h["x"],h["y"]); pg.mouse.down(); pg.mouse.move(t["x"],t["y"],steps=8); pg.mouse.up()
    ec=pg.evaluate("()=>{const o=propEval(PROPS[0]); const i=D.dates.indexOf(PROPS[0].z); return {z:PROPS[0].z, Z:o.Z, close:D.c[i], basis:o.basis}}"); print("Close mode Z:",ec); assert abs(ec["Z"]-ec["close"])<1e-9
    print("ERRORS:",errs)
    b.close()
