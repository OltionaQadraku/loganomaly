import os
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db
from api.db_models import User

SECRET_KEY = os.environ.get('LOGSENSE_SECRET_KEY', 'dev-only-secret-change-this-in-production-0000')
ALGORITHM = 'HS256'
TOKEN_EXPIRY_DAYS = 7
COOKIE_NAME = 'access_token'

NOT_AUTHENTICATED = {
    'reason': 'NOT_AUTHENTICATED',
    'message': 'You need to be logged in to do that.',
}


def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def create_token(user_id):
    payload = {
        'sub': str(user_id),
        'exp': datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(access_token: str = Cookie(default=None), db: Session = Depends(get_db)):
    if not access_token:
        raise HTTPException(401, NOT_AUTHENTICATED)

    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, {
            'reason': 'SESSION_EXPIRED',
            'message': 'Your session has expired. Please log in again.',
        })
    except jwt.InvalidTokenError:
        raise HTTPException(401, NOT_AUTHENTICATED)

    user = db.get(User, int(payload['sub']))
    if user is None:
        raise HTTPException(401, NOT_AUTHENTICATED)
    return user
