import json
from fastapi.responses import HTMLResponse

def htmx_toast_response(message: str, type: str = "success", refresh_page: bool = False, redirect_url: str = None) -> HTMLResponse:
    """
    Return an HTMX-compatible response that triggers a client-side global toast.
    If refresh_page is True, it also tells HTMX to refresh the current page via HX-Refresh.
    If redirect_url is given, it tells HTMX to client-side redirect via HX-Redirect.
    """
    trigger_payload = {"showMessage": {"msg": message, "type": type}}
    headers = {"HX-Trigger": json.dumps(trigger_payload)}
    
    if redirect_url:
        headers["HX-Redirect"] = redirect_url
    elif refresh_page:
        headers["HX-Refresh"] = "true"
        
    # Return 204 No Content so HTMX doesn't swap any visible DOM elements
    # unless it is commanded to refresh or redirect.
    return HTMLResponse("", status_code=204, headers=headers)
