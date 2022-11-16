import jwt
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jwt import DecodeError
from starlette.websockets import WebSocket
from passlib.hash import bcrypt
from tortoise.contrib.fastapi import register_tortoise
from tortoise.exceptions import IntegrityError, DoesNotExist

from app import settings
from app.actions import authenticate_user
from app.models import User, Room, PrivateRoom
from app.schemas import Registration, AccountInfo, AccessData, PrivateRoomConnectPost, PrivateRoomInfo, FoundRoom

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user = await User.get(id=payload.get('id'))

    except DoesNotExist | DecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Invalid credentials')

    return await AccountInfo.from_tortoise_orm(user)


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(registration_data: Registration):
    user_obj = User(username=registration_data.username,
                    password_hash=bcrypt.hash(registration_data.password))

    try:
        await user_obj.save()
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username taken")


@app.post("/auth/login", response_model=AccessData, status_code=status.HTTP_200_OK)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Incorrect password or username")

    user_obj = await AccountInfo.from_tortoise_orm(user)
    token = jwt.encode(user_obj.dict(), settings.JWT_SECRET)

    return AccessData(access_token=token, token_type='bearer')


@app.get("/users/me", response_model=AccountInfo, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: AccountInfo = Depends(get_current_user)):
    return current_user


@app.get("/users/info/{username}", response_model=AccountInfo, status_code=status.HTTP_302_FOUND)
async def get_user_info(username: str):
    try:
        user = await User.get(username=username)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")

    return AccountInfo.from_tortoise_orm(user)


@app.post("/room/private/connect", response_model=PrivateRoomInfo, status_code=status.HTTP_200_OK)
async def connect_ro_private_room(
        connect_data: PrivateRoomConnectPost = Depends(),
        current_user: AccountInfo = Depends(get_current_user)
):
    user = await User.get(id=current_user.id)

    if user.connected_room:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already connected")

    try:
        private_room = await PrivateRoom.get(connection_key=connect_data.connect_key)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid connect key")

    room = await private_room.room.first()
    user.connected_room = room
    await user.save()

    return PrivateRoomInfo(room_id=room.id, connect_key=private_room.connection_key)


@app.post("/room/private/create", response_model=PrivateRoomInfo)
async def create_private_room(current_user: AccountInfo = Depends(get_current_user)):
    user = await User.get(id=current_user.id)

    if user.connected_room:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already connected")

    room = await Room.create()
    private_room = await PrivateRoom.create(room=room, connection_key=str(room.id))

    user.connected_room = room
    await user.save()

    return PrivateRoomInfo(room_id=room.id, connect_key=private_room.connection_key)


@app.post("/room/search", response_model=FoundRoom)
async def find_opponent(user: AccountInfo = Depends(get_current_user)):
    raise NotImplementedError


@app.websocket("/room/connect")
async def connect_to_game_session(websocket: WebSocket, session_id: int, access_data: AccessData):
    raise NotImplementedError


register_tortoise(
    app,
    db_url='sqlite://db.sqlite3',
    modules={'models': ['app.models']},
    generate_schemas=True,
    add_exception_handlers=True
)
