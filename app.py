"""
🎵 VOFO Music - Python Backend (Simplified - No JWT)
"""

import os
import logging
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from datetime import datetime
from ytmusicapi import YTMusic
from pydantic import BaseModel, Field
from typing import Optional, List

# ============================================
# CONFIGURATION
# ============================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vofo_music.db")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    if "?" not in DATABASE_URL:
        DATABASE_URL += "?sslmode=require"

print(f"📦 DATABASE_URL: {DATABASE_URL[:50]}..." if DATABASE_URL else "❌ No DATABASE_URL")

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

# Initialize YTMusic
try:
    yt = YTMusic()
    print("✅ YouTube Music API initialized")
except Exception as e:
    print(f"⚠️ YouTube Music API error: {e}")
    yt = None

# ============================================
# MODELS - Simplified
# ============================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Favorite(Base):
    __tablename__ = "favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), index=True, nullable=False)  # Simple username
    song_id = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    artist = Column(String(255))
    thumbnail = Column(String(500))
    duration = Column(String(20))
    added_at = Column(DateTime(timezone=True), server_default=func.now())


# Create tables
Base.metadata.create_all(bind=engine)

# ============================================
# PYDANTIC SCHEMAS
# ============================================

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)

class FavoriteCreate(BaseModel):
    username: str
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

# ============================================
# DATABASE FUNCTIONS
# ============================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="VOFO Music API", version="2.0.0")

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
async def health_check():
    return {"status": "OK", "message": "✦ VOFO Music is live"}

# ---------- AUTH (Simplified) ----------

@app.post("/api/auth/register")
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if username exists
    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(400, "Username already taken")
    
    # Create user
    user = User(username=user_data.username)
    db.add(user)
    db.commit()
    
    return {"success": True, "username": user_data.username}

@app.post("/api/auth/login")
async def login(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user:
        raise HTTPException(401, "User not found")
    
    return {"success": True, "username": user_data.username}

@app.get("/api/auth/me")
async def get_me(username: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    return {"username": user.username, "created_at": user.created_at}

# ---------- YOUTUBE MUSIC ----------

@app.get("/api/trending")
async def get_trending():
    try:
        if not yt:
            return []
        
        charts = yt.get_charts(country="IN")
        songs = charts.get('songs', {}).get('items', [])
        
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
        
        return results
    except Exception as e:
        logging.error(f"Trending error: {str(e)}")
        return []

@app.get("/api/search")
async def search_songs(q: str = Query(..., min_length=1)):
    try:
        if not yt:
            return []
            
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

# ---------- FAVORITES (Simplified - No JWT) ----------

@app.post("/api/favorites")
async def add_favorite(song: FavoriteCreate, db: Session = Depends(get_db)):
    # Check if already favorited
    existing = db.query(Favorite).filter(
        Favorite.username == song.username,
        Favorite.song_id == song.song_id
    ).first()
    
    if existing:
        return {"message": "Already in favorites", "favorited": True}
    
    # Add to favorites
    favorite = Favorite(
        username=song.username,
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
    username: str = Query(...),
    db: Session = Depends(get_db)
):
    result = db.query(Favorite).filter(
        Favorite.username == username,
        Favorite.song_id == song_id
    ).delete()
    db.commit()
    
    if result:
        return {"message": "Removed from favorites", "favorited": False}
    else:
        raise HTTPException(404, "Song not found in favorites")

@app.get("/api/favorites")
async def get_favorites(
    username: str = Query(...),
    db: Session = Depends(get_db)
):
    favorites = db.query(Favorite).filter(
        Favorite.username == username
    ).order_by(Favorite.added_at.desc()).all()
    
    return [FavoriteResponse.model_validate(f) for f in favorites]

@app.get("/api/favorites/check/{song_id}")
async def check_favorite(
    song_id: str,
    username: str = Query(...),
    db: Session = Depends(get_db)
):
    favorite = db.query(Favorite).filter(
        Favorite.username == username,
        Favorite.song_id == song_id
    ).first()
    
    return {"isFavorited": favorite is not None}

# ============================================
# SERVE FRONTEND
# ============================================

@app.get("/")
async def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
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
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
