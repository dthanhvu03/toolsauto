from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer
import app.config as config
import secrets
from app.main_templates import templates

router = APIRouter(tags=["auth"])

def get_signer():
    if not config.SECRET_KEY:
        raise Exception("SECRET_KEY must be set in .env")
    return URLSafeTimedSerializer(config.SECRET_KEY)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, username: str = None, password: str = None):
    """
    Render the premium login UI.
    Supports E2E debug login if username and password query params match config.
    """
    if username and password:
        if secrets.compare_digest(username.strip(), config.ADMIN_USERNAME) and \
           secrets.compare_digest(password.strip(), config.ADMIN_PASSWORD):
            
            signer = get_signer()
            token = signer.dumps({"user": "admin", "role": "superuser"})
            
            response = RedirectResponse(url="/")
            response.set_cookie(
                key="session_token",
                value=token,
                max_age=604800,
                path="/",
                httponly=True,
                samesite="lax",
                secure=True if request.url.scheme == "https" else False
            )
            return response

    return templates.TemplateResponse("pages/login.html", {"request": request})

@router.post("/login")
async def login_api(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login and set secure cookie"""
    if not config.ADMIN_USERNAME or not config.ADMIN_PASSWORD:
        return JSONResponse({"ok": False, "message": "System not configured correctly"}, status_code=500)
        
    try:
        correct_username = secrets.compare_digest(username.strip(), config.ADMIN_USERNAME)
        correct_password = secrets.compare_digest(password.strip(), config.ADMIN_PASSWORD)
        
        if correct_username and correct_password:
            signer = get_signer()
            # Encoded token with user reference
            token = signer.dumps({"user": "admin", "role": "superuser"})
            
            response = JSONResponse({"ok": True, "redirect": "/"})
            
            # Set cookie: HttpOnly, Secure if https, Lax for CSRF defense
            # 7 days = 604800 seconds
            response.set_cookie(
                key="session_token",
                value=token,
                max_age=604800,
                path="/",
                httponly=True,
                samesite="lax",
                secure=True if request.url.scheme == "https" else False
            )
            return response
            
    except Exception:
        pass
        
    return JSONResponse(
        {"ok": False, "message": "Thông tin đăng nhập không hợp lệ"},
        status_code=401
    )

@router.post("/logout")
async def logout(request: Request):
    """Clear session cookie and redirect"""
    response = JSONResponse({"ok": True, "redirect": "/login"})
    response.delete_cookie(
        key="session_token",
        path="/",
        httponly=True,
        samesite="lax",
        secure=True if request.url.scheme == "https" else False
    )
    return response
