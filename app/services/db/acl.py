# Database Access Control List (ACL)
# Only whitelisted tables allow write actions (INSERT, UPDATE, DELETE)

# Tables that are strictly read-only for the explorer
READONLY_TABLES = {
    "audit_logs",
    "alembic_version", 
    "runtime_settings_audit",
    "job_events",
    "system_state"
}

# Tables that allow data modifications
WRITABLE_TABLES = {
    "accounts",
    "jobs",
    "affiliate_links",
    "discovered_channels",
    "viral_materials",
    "runtime_settings"
}

def check_table_permission(table_name: str, action: str) -> bool:
    """
    Rule: default deny — only tables in WRITABLE_TABLES allow write actions.
    SELECT is allowed on all tables (unless we want to hide some completely).
    """
    action = action.lower()
    
    # Read actions are allowed for all tables presently
    if action == "select":
        return True
        
    # Write actions only for whitelisted tables
    if action in {"insert", "update", "delete"}:
        return table_name in WRITABLE_TABLES
        
    return False
