from jose import jwt, JWTError
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
import os

SECRET_KEY = os.getenv("SECRET_KEY", "mysecretkey")
ALGORITHM = os.getenv("ALGORITHM", "HS256")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def create_access_token(user):
        payload = {"sub": user}
        token= jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        return token
    

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré") 
    