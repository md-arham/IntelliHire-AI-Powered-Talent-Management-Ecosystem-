import os
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.utils.internships_run_scraper import (
    internships_scraper,
    deactivate_expired_internships_job,
)
from app.middlware.permission_enforcer import check_permissions_middleware

# from sqlalchemy.schema import CreateTable
from app.api import (
    auth_router,
    hackathon_router,
    campusplacement_router,
    companies_router,
    colleges_router,
    courses_router,
    campus_drive_router,
    employer_router,
    internship_router,
    interview_router,
    interview_scheduling_router,
    job_match_router,
    job_postings_router,
    mock_interview_router,
    resume_router,
    roadmap_router,
    roles_api,
    student_router,
    user_router,
    student_dashboard_router,
    bookmarks_router,
    employer_dashboard_router,
    learning_path_router,
    offer_letter_router,
    acceptance_workflow_router,
    video_analytics_router,
    articles_router,
    initialise_router,
    api_permission_router,
)


from app.database.db import engine, init_models

from app.utils.hackathon_utils import run_delete_old_hackathons
from app.utils.logger_config import logger
# from app.utils.articles_scheduler import refresh_articles


BASE_DIR = Path(__file__).resolve().parent
logger.info(f"Base Path: {BASE_DIR}")
scheduler = AsyncIOScheduler()


scheduler.add_job(run_delete_old_hackathons, "interval", days=1)
scheduler.add_job(internships_scraper, "interval", days=4)
# scheduler.add_job(refresh_articles, "interval", days=7)
scheduler.add_job(deactivate_expired_internships_job, "cron", hour=0)


# App runs here
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    scheduler.start()
    # refresh_articles()
    app.state.async_client = httpx.AsyncClient()
    await init_models()

    try:
        yield
    finally:
        await app.state.async_client.aclose()
        scheduler.shutdown()

        await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# app.add_middleware(SessionMiddleware, secret_key="wowSoCool")
app.middleware("http")(check_permissions_middleware)

app.include_router(auth_router.router)
app.include_router(campusplacement_router.router)
app.include_router(companies_router.router)
app.include_router(colleges_router.router)
app.include_router(campus_drive_router.router)
app.include_router(internship_router.router)
app.include_router(user_router.router)
app.include_router(student_router.router)
app.include_router(employer_router.router)
# app.include_router(hackathon_router.router)
app.include_router(resume_router.router)
app.include_router(courses_router.router)
app.include_router(job_postings_router.router)
app.include_router(roadmap_router.router)
app.include_router(interview_router.router)
app.include_router(video_analytics_router.router)
app.include_router(mock_interview_router.router)
app.include_router(job_match_router.router)
app.include_router(articles_router.router)
app.include_router(student_dashboard_router.router)
app.include_router(employer_dashboard_router.router)
app.include_router(bookmarks_router.router)
app.include_router(learning_path_router.router)
app.include_router(offer_letter_router.router)
app.include_router(acceptance_workflow_router.router)
app.include_router(interview_scheduling_router.router)
app.include_router(initialise_router.router)
app.include_router(roles_api.roles_router)
app.include_router(api_permission_router.router)
# app.mount("/assets", StaticFiles(directory=BASE_DIR / "dist/assets"), name="static")


# =---------------------------------Rapi-Docs-------------------------------
@app.get("/rapidoc", include_in_schema=False)
async def rapidoc_ui():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
      <head>
        <title>RapiDoc</title>
        <script type="module" src="https://unpkg.com/rapidoc/dist/rapidoc-min.js"></script>
      </head>
      <body>
        <rapi-doc
            spec-url="/openapi.json"
            theme="light"
            render-style="read"
            show-header="true"
            allow-spec-url-load="false"
            allow-authentication="true"
            show-method-in-nav-bar="as-colored-block"
            allow-try="true"
        >
        </rapi-doc>
      </body>
    </html>
    """)


# ------ Populate offer letter templates -------
# populate_templates()


@app.get("/{full_path:path}")
async def serve_react(full_path: str):
    # Skip API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    # Serve the index.html for all non-API routes
    index_path = f"{BASE_DIR}/dist/index.html"
    if os.path.exists(index_path):
        logger.info(f"Found Directory at {index_path}")
        return FileResponse(index_path)
    else:
        logger.error(f"React build not found at {index_path}")
        raise HTTPException(status_code=404, detail="React app not found")


if __name__ == "__main__":
    # uvicorn.run(
    #     app,
    #     host="0.0.0.0",
    #     port=8525,
    #     ssl_keyfile="/etc/letsencrypt/live/oneclicktalenthire.aidenai.com/privkey.pem",
    #     ssl_certfile="/etc/letsencrypt/live/oneclicktalenthire.aidenai.com/fullchain.pem",
    # )
    uvicorn.run(app, port=8525, host="0.0.0.0")
