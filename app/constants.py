from enum import StrEnum

class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    DRAFT = "DRAFT"
    AI_PROCESSING = "AI_PROCESSING"
    AWAITING_STYLE = "AWAITING_STYLE"
    CANCELLED = "CANCELLED"

class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENGAGING = "ENGAGING"
    INVALID = "INVALID"
    
class ViralStatus(StrEnum):
    NEW = "NEW"
    REUP = "REUP"
    DRAFTED = "DRAFTED"
    FAILED = "FAILED"

# Sentinel marker for content orchestrator & queue
AI_GENERATE_MARKER = "[AI_GENERATE]"

# Error classification markers
GEMINI_INFRA_MARKERS = [
    "HTTPConnectionPool(host='localhost'",
    "Read timed out",
    "cannot connect to chrome",
    "undetected_chromedriver unexpectedly exited",
]

GEMINI_AUTH_MARKERS = [
    "cookies expired",
    "signin",
    "ServiceLogin",
    "Captcha",
]

# Anti-hallucination guard markers
HALLUCINATION_MARKERS = [
    "chuyên gia content facebook ads",
    "chuyên gia digital marketing",
    "accesstrade đã sẵn sàng",
    "hỗ trợ bạn tối ưu ngân sách",
    "cho tôi thông tin",
    "lên ngay dàn bài",
    "bạn muốn vít ads",
    "chiến dịch affiliate",
    "tư duy a/b testing",
    "chào vũ",
]

# Vietnamese stop words for keyword extraction
VI_STOP_WORDS = {
    "và", "là", "của", "cho", "với", "một", "những", "các", "đang", "đã", "sẽ",
    "thì", "mà", "khi", "nhưng", "để", "lại", "rồi", "người", "có", "không", "này"
}
