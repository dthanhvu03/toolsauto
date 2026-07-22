from app.core.ai.pipeline import AICaptionPipeline

# Global Singleton instance for AI Caption Generation.
# This ensures that Circuit Breaker state (OPEN/CLOSED) and Configs
# are persisted across HTTP requests within the current process.
pipeline = AICaptionPipeline()
