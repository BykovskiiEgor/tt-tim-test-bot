from sqlalchemy import Integer, BigInteger, String, Text, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from datetime import datetime
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions: Mapped[list["FolderSubscription"]] = relationship(
        "FolderSubscription", back_populates="user", cascade="all, delete-orphan"
    )

class FolderSubscription(Base):
    __tablename__ = "folder_subscriptions"
    __table_args__ = (
        UniqueConstraint('user_id', 'folder_path', name='_user_folder_uc'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.tg_id"), index=True)
    folder_path: Mapped[str] = mapped_column(Text, index=True)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ База данных SQLite инициализирована")


async def get_session():
    async with async_session() as session:
        yield session