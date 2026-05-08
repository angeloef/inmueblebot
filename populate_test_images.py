import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.models.property import Property as PropertyModel
from app.core.config import get_settings


async def main():
    settings = get_settings()
    api_base = settings.API_BASE_URL.rstrip("/")
    # 4 test image URLs hosted under /static/imagenes served by FastAPI
    image_urls = [
        f"{api_base}/static/imagenes/img1.jpg",
        f"{api_base}/static/imagenes/img2.jpg",
        f"{api_base}/static/imagenes/img3.jpg",
        f"{api_base}/static/imagenes/img4.jpg",
    ]


    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_factory() as session:
        # Load first 50 properties (seed order by id)
        result = await session.execute(select(PropertyModel).order_by(PropertyModel.id).limit(50))
        props = result.scalars().all()
        for p in props:
            p.images = image_urls
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
