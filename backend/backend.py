from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import redis
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import ClientSession
import os
from dotenv import load_dotenv
import psycopg2
from fastapi.responses import FileResponse
import csv

load_dotenv()

app = FastAPI()
r = redis.Redis(host='localhost', port=6379, db=0)
ADMIN_PASSWORD = "admin" #os.getenv("ADMIN_PASSWORD")

class UserUpdate(BaseModel):
    full_name: str

class User(BaseModel):
    full_name: str

class AdminRequest(BaseModel):
    password: str


def is_admin(username: str) -> bool:
    return r.sismember("admins", username)

def get_user_key(username: str) -> str:
    return f"user:{username}"


@app.post("/users/")
async def create_user(user: User, x_username: str = Header(...)):
    user_key = get_user_key(x_username)
    if r.exists(user_key):
        raise HTTPException(status_code=400, detail="Пользователь уже существует.")
    
    user_data = {"full_name": user.full_name, "is_admin": "False"}
    r.hset(user_key, mapping=user_data)
    return {"status": "success"}

@app.get("/users/me")
async def read_user_me(x_username: str = Header(...)):
    user_key = get_user_key(x_username)
    user_data = r.hgetall(user_key)
    if not user_data:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"username": x_username, "full_name": user_data[b"full_name"].decode(), "is_admin": user_data[b"is_admin"].decode()}

@app.put("/users/me")
async def update_user_me(user: User, x_username: str = Header(...)):
    user_key = get_user_key(x_username)
    if not r.exists(user_key):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    r.hset(user_key, "full_name", user.full_name)
    return {"status": "success"}

@app.post("/add_admin")
async def add_admin(request: AdminRequest, x_username: str = Header(...)):
    #print("Полученный запрос:", request.dict())  # Выведет тело запроса
    #print("Ожидаемый пароль:", ADMIN_PASSWORD)

    if request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Неверный пароль")
    
    user_key = f"user:{x_username}"
    if not r.exists(user_key):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    r.sadd("admins", x_username)
    r.hset(user_key, "is_admin", "True")
    
    return {"status": "success"}

@app.get("/check_admin")
async def check_admin(x_username: str = Header(...)):
    if not is_admin(x_username):
        raise HTTPException(status_code=403, detail="Нет прав администратора")
    return {"status": "ok"}

@app.put("/admin/users/{username}")
async def admin_update_user(username: str, user: UserUpdate, x_username: str = Header(...)):
    if not is_admin(x_username):
        raise HTTPException(status_code=403, detail="Нет прав администратора")
    
    user_key = get_user_key(username)
    if not r.exists(user_key):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    r.hset(user_key, "full_name", user.full_name)
    return {"status": "success", "new_name": user.full_name}

@app.get("/admin/users/csv")
async def get_all_users_csv(x_username: str = Header(...)):
    if not is_admin(x_username):
        raise HTTPException(status_code=403, detail="Запрещено")
    
    filename = "users.csv"
    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Username", "Full Name", "Is Admin"])
        for key in r.scan_iter("user:*"):
            username = key.decode().split(":")[1]
            user_data = r.hgetall(key)
            writer.writerow([username, user_data[b"full_name"].decode(), user_data[b"is_admin"].decode()])
    
    return FileResponse(filename, filename="users.csv", media_type="application/octet-stream")


@app.delete("/users/me")
async def delete_user_redis(x_username: str = Header(...)):
    user_key = get_user_key(x_username)
    if not r.exists(user_key):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    else:
        r.delete(user_key)
        return {"status": "success"}

@app.delete("/admin/clear_redis")
async def clear_redis(x_username: str = Header(...)):
    if not is_admin(x_username):
        raise HTTPException(status_code=403, detail="Нет прав администратора")

    r.flushdb()  # Полностью очищает всю базу Redis

    return {"status": "success", "message": "База данных Redis успешно очищена"}