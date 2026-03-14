import os, re, hashlib, uvicorn
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_application
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import sessionmaker, declarative_base

# Database setup
DATABASE_URL = "sqlite:///./u.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
class U(Base):
    __tablename__ = "u"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    p_hash = Column(String)
Base.metadata.create_all(bind=engine)
def h_pw(p): return hashlib.sha256(p.encode()).hexdigest()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

x, y, z, v, t = sp.symbols("x y z v t")
allowed = {"x":x,"y":y,"z":z,"v":v,"t":t,"sqrt":sp.sqrt,"pi":sp.pi,"oo":sp.oo}
trans = (standard_transformations + (implicit_application,))

class UserCreate(BaseModel): username: str; password: str
class MathReq(BaseModel): question: str

UI_HTML = """<!DOCTYPE html><html><head><title>AI MathBot</title><style>body{font-family:sans-serif;background:#eef2f3;display:flex;flex-direction:column;align-items:center;padding:20px}.card{max-width:400px;background:white;padding:25px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1)}input{width:100%;padding:10px;margin:10px 0;border:1px solid #3498db;border-radius:5px;box-sizing:border-box}button{width:100%;padding:10px;background:#000;color:white;border:none;border-radius:5px;cursor:pointer}#math-section{display:none}</style></head><body><div id='auth-section' class='card'><h2>Login</h2><input type='text' id='u' placeholder='Username'><input type='password' id='p' placeholder='Password'><button onclick='h()'>Login / Sign Up</button></div><div id='math-section' class='card'><h2>MathBot</h2><input type='text' id='q' placeholder='Math problem...'><button onclick='s()'>Solve</button><div id='ans' style='margin-top:15px;font-weight:bold;color:green'></div><button onclick='location.reload()' style='background:#7f8c8d;margin-top:10px'>Logout</button></div><script>let t='';async function h(){const u=document.getElementById('u').value,p=document.getElementById('p').value;const r=await fetch('/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`username=${u}&password=${p}`});const d=await r.json();if(r.ok){t=d.access_token;document.getElementById('auth-section').style.display='none';document.getElementById('math-section').style.display='block';}else{const rr=await fetch('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});if(rr.ok)alert('Registered! Now Login');else alert('Error');}}async function s(){const q=document.getElementById('q').value;const r=await fetch('/solve',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({question:q})});const d=await r.json();document.getElementById('ans').innerText=d.result||d.error;}</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def serve(): return UI_HTML

@app.post("/register")
def reg(u: UserCreate):
    db = SessionLocal()
    try:
        if db.query(U).filter(U.username == u.username).first(): raise HTTPException(400, "User exists")
        new = U(username=u.username, p_hash=h_pw(u.password))
        db.add(new); db.commit(); return {"msg":"ok"}
    except: raise HTTPException(400)

@app.post("/token")
def login(f: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal(); user = db.query(U).filter(U.username == f.username).first()
    if not user or user.p_hash != h_pw(f.password): raise HTTPException(400)
    return {"access_token": user.username}

@app.post("/solve")
def solve(d: MathReq):
    try:
        q = d.question.replace("♾️","oo").replace("π","pi").replace("÷","/").replace("×","*")
        q = re.sub(r"sqrt(\\d+)", r"sqrt(\\1)", q.replace("√", "sqrt"))
        expr = parse_expr(q, local_dict=allowed, transformations=trans)
        res = expr.doit().evalf()
        return {"result": str(res).replace("oo", "♾️")}
    except Exception as e: return {"error": str(e)}
