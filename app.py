"""
🎵 VOFO Music - Python Backend
Deployment-ready for Render with PostgreSQL
"""

import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text, Boolean, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from ytmusicapi import YTMusic
from pydantic import BaseModel, Field
from typing import Optional, List
import urllib.parse

# ============================================
# CONFIGURATION
# ============================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vofo_music.db")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    if "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080

# ============================================
# DATABASE SETUP
# ============================================

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialize YTMusic with error handling
try:
    yt = YTMusic()
    print("✅ YouTube Music API initialized successfully")
except Exception as e:
    print(f"⚠️ YouTube Music API init error: {e}")
    yt = None

# ============================================
# MODELS
# ============================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="user", cascade="all, delete-orphan")


class Favorite(Base):
    __tablename__ = "favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    song_id = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(255))
    thumbnail = Column(String(500))
    duration = Column(String(20))
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="favorites")


class Playlist(Base):
    __tablename__ = "playlists"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="playlists")
    songs = relationship("PlaylistSong", back_populates="playlist", cascade="all, delete-orphan")


class PlaylistSong(Base):
    __tablename__ = "playlist_songs"
    
    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    song_id = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(255))
    thumbnail = Column(String(500))
    duration = Column(String(20))
    position = Column(Integer, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    playlist = relationship("Playlist", back_populates="songs")


# Create tables
Base.metadata.create_all(bind=engine)

# ============================================
# PYDANTIC SCHEMAS
# ============================================

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class FavoriteCreate(BaseModel):
    song_id: str
    title: str
    artist: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[str] = None

class FavoriteResponse(BaseModel):
    id: int
    song_id: str
    title: str
    artist: Optional[str]
    thumbnail: Optional[str]
    duration: Optional[str]
    added_at: datetime
    
    class Config:
        from_attributes = True

class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_public: bool = False

class PlaylistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_public: bool
    song_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True

class PlaylistDetailResponse(PlaylistResponse):
    songs: List[dict] = []

# ============================================
# AUTH FUNCTIONS
# ============================================

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    # Set expiration
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # Encode the token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        # Use the same SECRET_KEY and ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"JWT Decode Error: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected error decoding token: {str(e)}")
        return None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get current user from Authorization header.
    Supports both "Bearer <token>" format and direct token.
    """
    if not authorization:
        print("❌ No Authorization header provided")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if it's a Bearer token
    if authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "").strip()
    else:
        token = authorization.strip()
    
    if not token:
        print("❌ Empty token")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # Decode the token
    payload = decode_token(token)
    if not payload:
        print(f"❌ Failed to decode token: {token[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get user ID from token
    user_id = payload.get("sub")
    if not user_id:
        print("❌ No 'sub' field in token payload")
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        print(f"❌ User not found: {user_id}")
        raise HTTPException(status_code=401, detail="User not found")
    
    print(f"✅ User authenticated: {user.username}")
    return user

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="VOFO Music API",
    description="Premium YouTube Music Experience",
    version="2.0.0"
)

# CORS - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# API ROUTES
# ============================================

@app.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {
            "status": "OK",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "✦ VOFO Music is live"
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

# ---------- AUTH ----------

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if username exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(400, "Username already taken")
    
    # Check if email exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already registered")
    
    # Create new user
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create token
    token = create_access_token({"sub": user.id})
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    # Find user by username or email
    user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.username)
    ).first()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Create token
    token = create_access_token({"sub": user.id})
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }

@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)

# ---------- YOUTUBE MUSIC ----------

@app.get("/api/trending")
async def get_trending():
    """Get trending songs with fallback to search if charts fail"""
    try:
        if not yt:
            raise Exception("YouTube Music API not initialized")
        
        # Try to get charts
        charts = yt.get_charts(country="IN")
        songs = charts.get('songs', {}).get('items', [])
        
        # If no songs, fallback to search
        if not songs:
            results = yt.search("top songs 2026", filter="songs")
            songs = results[:20] if results else []
            
        results = []
        for s in songs[:20]:
            thumbnails = s.get('thumbnails', [])
            thumbnail = thumbnails[-1]['url'] if thumbnails else ""
            artists = s.get('artists', [])
            artist = artists[0]['name'] if artists else "Unknown Artist"
            
            results.append({
                "id": s.get('videoId', ''),
                "title": s.get('title', 'Unknown Title'),
                "artist": artist,
                "thumbnail": thumbnail,
                "duration": s.get('duration', '')
            })
        
        return results if results else []
        
    except Exception as e:
        logging.error(f"Trending error: {str(e)}")
        return []

@app.get("/api/search")
async def search_songs(q: str = Query(..., min_length=1)):
    """Search for songs on YouTube Music"""
    try:
        if not yt:
            raise Exception("YouTube Music API not initialized")
            
        results = yt.search(q, filter="songs")
        
        songs = []
        for r in results[:20]:
            thumbnails = r.get('thumbnails', [])
            thumbnail = thumbnails[-1]['url'] if thumbnails else ""
            artists = r.get('artists', [])
            artist = artists[0]['name'] if artists else "Unknown Artist"
            
            songs.append({
                "id": r.get('videoId', ''),
                "title": r.get('title', 'Unknown Title'),
                "artist": artist,
                "thumbnail": thumbnail,
                "duration": r.get('duration', '')
            })
        
        return songs
    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return []

# ---------- FAVORITES ----------

@app.post("/api/favorites")
async def add_favorite(
    song: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if already favorited
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.song_id == song.song_id
    ).first()
    
    if existing:
        return {"message": "Already in favorites", "favorited": True}
    
    # Add to favorites
    favorite = Favorite(
        user_id=current_user.id,
        song_id=song.song_id,
        title=song.title,
        artist=song.artist,
        thumbnail=song.thumbnail,
        duration=song.duration
    )
    db.add(favorite)
    db.commit()
    
    return {"message": "Added to favorites", "favorited": True}

@app.delete("/api/favorites/{song_id}")
async def remove_favorite(
    song_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.song_id == song_id
    ).delete()
    db.commit()
    
    if result:
        return {"message": "Removed from favorites", "favorited": False}
    else:
        raise HTTPException(404, "Song not found in favorites")

@app.get("/api/favorites")
async def get_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    favorites = db.query(Favorite).filter(
        Favorite.user_id == current_user.id
    ).order_by(Favorite.added_at.desc()).all()
    
    return [FavoriteResponse.model_validate(f) for f in favorites]

@app.get("/api/favorites/check/{song_id}")
async def check_favorite(
    song_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.song_id == song_id
    ).first()
    
    return {"isFavorited": favorite is not None}

# ---------- PLAYLISTS ----------

@app.post("/api/playlists")
async def create_playlist(
    playlist: PlaylistCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_playlist = Playlist(
        user_id=current_user.id,
        name=playlist.name,
        description=playlist.description,
        is_public=playlist.is_public
    )
    db.add(db_playlist)
    db.commit()
    db.refresh(db_playlist)
    
    return PlaylistResponse(
        id=db_playlist.id,
        name=db_playlist.name,
        description=db_playlist.description,
        is_public=db_playlist.is_public,
        song_count=0,
        created_at=db_playlist.created_at
    )

@app.get("/api/playlists")
async def get_playlists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    playlists = db.query(Playlist).filter(
        (Playlist.user_id == current_user.id) | (Playlist.is_public == True)
    ).order_by(Playlist.created_at.desc()).all()
    
    result = []
    for p in playlists:
        song_count = db.query(PlaylistSong).filter(
            PlaylistSong.playlist_id == p.id
        ).count()
        result.append(PlaylistResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            is_public=p.is_public,
            song_count=song_count,
            created_at=p.created_at
        ))
    return result

@app.get("/api/playlists/{playlist_id}")
async def get_playlist_detail(
    playlist_id: int,
    db: Session = Depends(get_db)
):
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(404, "Playlist not found")
    
    songs = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id
    ).order_by(PlaylistSong.position).all()
    
    return PlaylistDetailResponse(
        id=playlist.id,
        name=playlist.name,
        description=playlist.description,
        is_public=playlist.is_public,
        song_count=len(songs),
        created_at=playlist.created_at,
        songs=[{
            "id": s.song_id,
            "title": s.title,
            "artist": s.artist,
            "thumbnail": s.thumbnail,
            "duration": s.duration
        } for s in songs]
    )

@app.post("/api/playlists/{playlist_id}/songs")
async def add_to_playlist(
    playlist_id: int,
    song: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if playlist exists and belongs to user
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist not found or you don't own it")
    
    # Check if song already in playlist
    existing = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id,
        PlaylistSong.song_id == song.song_id
    ).first()
    
    if existing:
        return {"message": "Already in playlist"}
    
    # Get max position
    max_pos = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id
    ).count()
    
    # Add song to playlist
    playlist_song = PlaylistSong(
        playlist_id=playlist_id,
        song_id=song.song_id,
        title=song.title,
        artist=song.artist,
        thumbnail=song.thumbnail,
        duration=song.duration,
        position=max_pos
    )
    db.add(playlist_song)
    db.commit()
    
    return {"message": "Added to playlist"}

@app.delete("/api/playlists/{playlist_id}/songs/{song_id}")
async def remove_from_playlist(
    playlist_id: int,
    song_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if playlist exists and belongs to user
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist not found or you don't own it")
    
    # Remove song from playlist
    result = db.query(PlaylistSong).filter(
        PlaylistSong.playlist_id == playlist_id,
        PlaylistSong.song_id == song_id
    ).delete()
    db.commit()
    
    if result:
        return {"message": "Removed from playlist"}
    else:
        raise HTTPException(404, "Song not in playlist")

@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if playlist exists and belongs to user
    playlist = db.query(Playlist).filter(
        Playlist.id == playlist_id,
        Playlist.user_id == current_user.id
    ).first()
    
    if not playlist:
        raise HTTPException(404, "Playlist not found or you don't own it")
    
    # Delete playlist
    db.delete(playlist)
    db.commit()
    
    return {"message": "Playlist deleted"}

# ============================================
# SERVE FRONTEND
# ============================================

@app.get("/")
async def serve_frontend():
    """Serve the main index.html file"""
    try:
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>✦ VOFO Music</title></head>
        <body style="display:flex;justify-content:center;align-items:center;min-height:100vh;background:radial-gradient(circle at 50% 50%, #1c1c1c 0%, #0a0a0a 100%);color:white;font-family:sans-serif;margin:0;text-align:center;padding:20px;">
            <div>
                <h1 style="font-size:4rem;background:linear-gradient(135deg,#c5a367,#f0d080);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">✦ VOFO</h1>
                <p style="color:rgba(255,255,255,0.6);font-size:1.2rem;">Music Experience</p>
                <p style="color:rgba(255,255,255,0.3);font-size:0.9rem;margin-top:20px;">✅ Backend is running!</p>
                <p style="color:rgba(255,255,255,0.2);font-size:0.8rem;margin-top:10px;">Please create index.html in the same directory</p>
            </div>
        </body>
        </html>
        """)

# ============================================
# RUN THE APP
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
