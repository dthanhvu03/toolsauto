from typing import List, Dict, Any

class PageUtils:
    """
    Helper service to extract Page-related JSON arrays from an Account model 
    and format them into a flat view-model suitable for pages_table.html rendering.
    """

    @staticmethod
    def build_page_view_models(account, q: str = "", filter_str: str = "all") -> List[Dict[str, Any]]:
        """
        Parses account JSON properties (managed_pages_list, target_pages_list, etc.)
        and builds a standard tabular representation for Target Pages.
        """
        managed = account.managed_pages_list or []
        target_urls = set(account.target_pages_list or [])
        page_niches = account.page_niches_map or {}
        competitors = account.competitor_urls_grouped or {}
        
        pages_list = []
        q = (q or "").strip().lower()
        filter_str = (filter_str or "all").lower()

        for p in managed:
            url = p.get('url', '')
            name = p.get('name', 'Unknown')
            if not url:
                continue
            
            is_active = url in target_urls
            
            # Filter matches
            if filter_str == "active" and not is_active:
                continue
            if filter_str == "paused" and is_active:
                continue
            
            niches = ", ".join(page_niches.get(url, []))
            comps = competitors.get(url, "")
            
            if q:
                # Allow searching by page name, url, niche, or parent account name
                haystack = f"{name} {url} {niches} {account.name}".lower()
                if q not in haystack:
                    continue
                
            pages_list.append({
                "account_id": account.id,
                "account_name": account.name,
                "platform": account.platform or "unknown",
                "url": url,
                "name": name,
                "is_active": is_active,
                "niches": niches,
                "competitors": comps
            })
            
        return pages_list
