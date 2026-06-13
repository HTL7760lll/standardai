"""
认证接口 — 登录 / 注册
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
import services.auth_service as auth
from models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if len(req.username) < 2:
        raise HTTPException(400, "用户名至少2位")
    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6位")
    user = auth.create_user(db, req.username, req.password)
    if user is None:
        raise HTTPException(409, "用户名已存在")
    token = auth.create_token(user.id, user.username, user.role)
    return {"message": "注册成功", "token": token, "username": user.username, "role": user.role}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = auth.get_user_by_username(db, req.username)
    if not user or not user.is_active:
        raise HTTPException(401, "用户名或密码错误")
    if not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = auth.create_token(user.id, user.username, user.role)
    return {"message": "登录成功", "token": token, "username": user.username, "role": user.role}


def require_role(*roles: str):
    """依赖注入：检查当前用户角色。用法: Depends(require_role('admin','engineer'))"""
    def checker(db: Session = Depends(get_db), authorization: str | None = None) -> User:
        user = get_current_user(db, authorization)
        if user.role not in roles:
            raise HTTPException(403, f"权限不足，需要角色: {', '.join(roles)}")
        return user
    return checker


def get_current_user(db: Session = Depends(get_db), authorization: str | None = None) -> User:
    """从 Authorization header 解析 JWT 并返回用户"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录，请先登录")
    token = authorization[7:]
    payload = auth.decode_token(token)
    if payload is None:
        raise HTTPException(401, "登录已过期，请重新登录")
    user_id = int(payload.get("sub", 0))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(401, "用户不存在或已禁用")
    return user


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}
