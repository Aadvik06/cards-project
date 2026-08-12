from app.services.monthly_log_service import MonthlyLogService
from app.services.recommendation_service import RecommendationService
from app.services.transaction_service import TransactionService


recommendation_service = RecommendationService()
transaction_service = TransactionService(recommendation_service)
monthly_log_service = MonthlyLogService(recommendation_service.ledger)


def get_recommendation_service() -> RecommendationService:
    return recommendation_service


def get_transaction_service() -> TransactionService:
    return transaction_service


def get_monthly_log_service() -> MonthlyLogService:
    return monthly_log_service

