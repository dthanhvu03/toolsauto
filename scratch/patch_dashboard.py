#!/usr/bin/env python3
"""Patch dashboard.py to fix settings save responses."""
import sys

path = "/home/vu/toolsauto/app/routers/dashboard.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

changes = 0

# 1. Add JSONResponse import
old_imp = "from fastapi.responses import HTMLResponse, RedirectResponse"
new_imp = "from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse"
if old_imp in text and "JSONResponse" not in text:
    text = text.replace(old_imp, new_imp)
    changes += 1
    print("[OK] Added JSONResponse import")

# 2. Individual save: return JSON instead of HTMX 204
old_save_error = '''    except ValueError:
        return htmx_toast_response("Kh\u00f4ng th\u1ec3 l\u01b0u: key ho\u1eb7c gi\u00e1 tr\u1ecb kh\u00f4ng h\u1ee3p l\u1ec7.", "error", refresh_page=False)
    return htmx_toast_response("\u0110\u00e3 l\u01b0u c\u00e0i \u0111\u1eb7t th\u00e0nh c\u00f4ng.", "success", refresh_page=True)'''

new_save_error = '''    except ValueError:
        return JSONResponse({"success": False, "error": "Kh\u00f4ng th\u1ec3 l\u01b0u: key ho\u1eb7c gi\u00e1 tr\u1ecb kh\u00f4ng h\u1ee3p l\u1ec7."}, status_code=400)
    
    import json as _json
    headers = {"HX-Trigger": _json.dumps({"showMessage": {"msg": "\u0110\u00e3 l\u01b0u c\u00e0i \u0111\u1eb7t th\u00e0nh c\u00f4ng.", "type": "success"}})}
    return JSONResponse({"success": True}, headers=headers)'''

if old_save_error in text:
    text = text.replace(old_save_error, new_save_error)
    changes += 1
    print("[OK] Updated individual save to JSON response")
else:
    print("[SKIP] Individual save block not found (may already be patched)")

# 3. Reset: disable auto-refresh so toast is visible
old_reset = 'return htmx_toast_response("\u0110\u00e3 \u0111\u1eb7t l\u1ea1i v\u1ec1 m\u1eb7c \u0111\u1ecbnh.", "success", refresh_page=True)'
new_reset = 'return htmx_toast_response("\u0110\u00e3 \u0111\u1eb7t l\u1ea1i v\u1ec1 m\u1eb7c \u0111\u1ecbnh.", "success", refresh_page=False)'
if old_reset in text:
    text = text.replace(old_reset, new_reset)
    changes += 1
    print("[OK] Updated reset to disable auto-refresh")
else:
    print("[SKIP] Reset block not found (may already be patched)")

# 4. Bulk save: disable auto-refresh so toast is visible
old_bulk = 'refresh_page=True)\n\n@router.get("/app/viral/table"'
new_bulk = 'refresh_page=False)\n\n@router.get("/app/viral/table"'
if old_bulk in text:
    text = text.replace(old_bulk, new_bulk)
    changes += 1
    print("[OK] Updated bulk-save to disable auto-refresh")
else:
    print("[SKIP] Bulk-save block not found (may already be patched)")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"\nDone. {changes} change(s) applied.")
