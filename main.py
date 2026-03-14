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

# Database setup with History support
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

UI_HTML = """<!DOCTYPE html><html><head><title>AI MathBot Pro</title><style>
body{font-family:sans-serif;background:#f0f4f8;display:flex;flex-direction:column;align-items:center;padding:20px}
.card{width:90%;max-width:600px;background:white;padding:30px;border-radius:15px;box-shadow:0 8px 30px rgba(0,0,0,0.1);margin-bottom:20px}
input, textarea{width:100%;padding:12px;margin:10px 0;border:1px solid #d1d9e6;border-radius:8px;box-sizing:border-box;font-size:16px}
textarea{height:120px;resize:vertical}
.btn-group{display:flex;gap:10px}
button{flex:1;padding:12px;background:#2d3436;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;transition:0.3s}
button:hover{background:#000}
.solve-btn{background:#0984e3}.solve-btn:hover{background:#74b9ff}
#math-section, #hist-box{display:none}
.hist-item{padding:10px;border-bottom:1px solid #eee;font-size:14px;color:#636e72}
</style></head><body>
<div id='auth-section' class='card'>
    <h2>MathBot Login</h2>
    <input type='text' id='u' placeholder='Username'>
    <input type='password' id='p' placeholder='Password'>
    <div class='btn-group'>
        <button onclick='auth("/token")'>Login</button>
        <button onclick='auth("/register")' style='background:#636e72'>Sign Up</button>
    </div>
</div>
<div id='math-section' class='card'>
    <h2>Solve Math</h2>
    <textarea id='q' placeholder='Enter your math problem or equation (e.g., x^2 + 5x + 6 = 0)...'></textarea>
    <button class='solve-btn' onclick='s()'>Solve Problem</button>
    <div id='ans' style='margin-top:20px;font-size:20px;font-weight:bold;color:#2d3436;text-align:center'></div>
</div>
<div id='hist-box' class='card'>
    <h3>Calculation History</h3>
    <div id='hist-list'></div>
</div>
<script>
let t='';
async function auth(path){
    const u=document.getElementById('u').value, p=document.getElementById('p').value;
    let r; 
    if(path==='/token'){
        r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`username=${u}&password=${p}`});
    } else {
        r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    }
    const d=await r.json();
    if(r.ok && d.access_token){ 
        t=d.access_token;
        document.getElementById('auth-section').style.display='none';
        document.getElementById('math-section').style.display='block';
        document.getElementById('hist-box').style.display='block';
        loadHist();
    } else if(r.ok) { alert('Success! You can now login.'); }
    else { alert(d.detail || 'Authentication Error'); }
}
async function s(){
    const q=document.getElementById('q').value;
    const r=await fetch('/solve',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({question:q})});
    const d=await r.json();
    document.getElementById('ans').innerText=d.result||d.error;
    loadHist();
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
    # In a real app we'd verify the token, for this demo we'll just pull all
    db = SessionLocal()
    items = db.query(History).order_by(History.id.desc()).limit(10).all()
    return [i.entry for i in items]

@app.post("/solve")
def solve(d: MathReq):
    db = SessionLocal()
    try:
        raw_q = d.question.replace("♾️","oo").replace("π","pi").replace("÷","/").replace("×","*")
        # Advanced equation handling
        if "=" in raw_q:
            lhs, rhs = raw_q.split("=")
            expr = sp.Eq(parse_expr(lhs, local_dict=allowed, transformations=trans), 
                         parse_expr(rhs, local_dict=allowed, transformations=trans))
            res = sp.solve(expr)
        else:
            expr = parse_expr(raw_q, local_dict=allowed, transformations=trans)
            res = sp.simplify(expr.doit())
        
        result_str = str(res).replace("oo", "♾️")
        db.add(History(entry=f"{d.question} = {result_str}"))
        db.commit()
        return {"result": result_str}
    except Exception as e: return {"error": str(e)}
