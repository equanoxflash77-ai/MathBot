# DEPLOY_ID: 20260314191153
import os, re, hashlib, uvicorn
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_application
from sqlalchemy import create_engine, Column, String, Integer, Text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./u.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class U(Base):
    __tablename__ = "u"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    p_hash = Column(String)

class History(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    entry = Column(Text)

Base.metadata.create_all(bind=engine)
def h_pw(p): return hashlib.sha256(p.encode()).hexdigest()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

x, y, z, v, t = sp.symbols("x y z v t")
allowed = {"x":x,"y":y,"z":z,"v":v,"t":t, "sqrt":sp.sqrt, "pi":sp.pi, "oo":sp.oo, "sin":sp.sin, "cos":sp.cos, "tan":sp.tan}
trans = (standard_transformations + (implicit_application,))

class UserCreate(BaseModel): username: str; password: str
class MathReq(BaseModel): question: str

UI_HTML = """<!DOCTYPE html><html><head><title>AI MathBot</title><style>
body{font-family:sans-serif;background:#eef2f3;display:flex;flex-direction:column;align-items:center;padding:20px}
.card{max-width:500px;width:100%;background:white;padding:25px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);margin-bottom:20px}
input{width:100%;padding:10px;margin:10px 0;border:1px solid #3498db;border-radius:5px;box-sizing:border-box;font-size:18px}
#q{width:100%;padding:12px;margin:15px 0;border:2px solid #3498db;border-radius:8px;font-size:22px;box-sizing:border-box}
button{width:100%;padding:10px;background:#000;color:white;border:none;border-radius:5px;cursor:pointer;font-weight:bold;margin-top:5px}
.hist-btn{background:#7f8c8d;margin-top:10px}
#math-section, #hist-box{display:none}
#ans{margin-top:15px;font-weight:bold;color:green;text-align:center;font-size:24px}
.hist-item{padding:10px;border-bottom:1px solid #eee;font-size:14px}
</style></head><body>
<div id='auth-section' class='card'>
    <h2>Login</h2>
    <input type='text' id='u' placeholder='Username'>
    <input type='password' id='p' placeholder='Password'>
    <button onclick='auth("/token")'>Login</button>
    <button onclick='auth("/register")' style='background:#7f8c8d'>Sign Up</button>
</div>
<div id='math-section' class='card'>
    <h2>AI MathBot</h2>
    <input type='text' id='q' placeholder='Enter question...'>
    <button onclick='s()'>=</button>
    <div id='ans'></div>
    <button class='hist-btn' onclick='toggleHist()'>Show / Hide History</button>
    <button onclick='location.reload()' style='background:#e74c3c;margin-top:20px'>Logout</button>
</div>
<div id='hist-box' class='card'>
    <h3>History</h3>
    <div id='hist-list'></div>
</div>
<script>
let t='';
async function auth(path){
    const u=document.getElementById('u').value, p=document.getElementById('p').value;
    let r; 
    if(path==='/token'){ r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`username=${u}&password=${p}` }); }
    else { r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p}) }); }
    const d=await r.json();
    if(r.ok && d.access_token){ 
        t=d.access_token;
        document.getElementById('auth-section').style.display='none';
        document.getElementById('math-section').style.display='block';
        loadHist();
    } else if(r.ok) { alert('Account created! Now login.'); }
    else { alert(d.detail || 'Error'); }
}
async function s(){
    const q=document.getElementById('q').value;
    const r=await fetch('/solve',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({question:q}) });
    const d=await r.json();
    document.getElementById('ans').innerText=d.result||d.error;
    loadHist();
}
function toggleHist(){
    const b = document.getElementById('hist-box');
    b.style.display = (b.style.display === 'block') ? 'none' : 'block';
}
async function loadHist(){
    const r=await fetch('/history',{headers:{'Authorization':'Bearer '+t}});
    const d=await r.json();
    document.getElementById('hist-list').innerHTML = d.map(i=>`<div class='hist-item'>${i}</div>`).join('');
}
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def serve(): return UI_HTML

@app.post("/register")
def reg(u: UserCreate):
    db = SessionLocal()
    try:
        if db.query(U).filter(U.username == u.username).first(): raise HTTPException(400, "User exists")
        new = U(username=u.username, p_hash=h_pw(u.password))
        db.add(new); db.commit(); return {"msg":"ok"}
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/token")
def login(f: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal(); user = db.query(U).filter(U.username == f.username).first()
    if not user or user.p_hash != h_pw(f.password): raise HTTPException(400, "Invalid credentials")
    return {"access_token": user.username}

@app.get("/history")
def get_hist(username: str = Depends(lambda f: None)): 
    db = SessionLocal()
    items = db.query(History).order_by(History.id.desc()).limit(20).all()
    return [i.entry for i in items]

@app.post("/solve")
def solve(d: MathReq):
    db = SessionLocal()
    try:
        raw_q = d.question.replace("♾️","oo").replace("π","pi").replace("÷","/").replace("×","*")
        if "=" in raw_q:
            lhs, rhs = raw_q.split("=")
            res = sp.solve(sp.Eq(parse_expr(lhs, local_dict=allowed, transformations=trans), 
                                 parse_expr(rhs, local_dict=allowed, transformations=trans)))
        else:
            res = sp.simplify(parse_expr(raw_q, local_dict=allowed, transformations=trans).doit())
        
        result_str = str(res).replace("oo", "♾️")
        db.add(History(entry=f"{d.question} = {result_str}"))
        db.commit()
        return {"result": result_str}
    except Exception as e: return {"error": str(e)}
