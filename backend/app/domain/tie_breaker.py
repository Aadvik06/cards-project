from app.domain.models import RecommendationOption


def option_sort_key(option: RecommendationOption) -> tuple:
    return (
        option.net_cost,
        -option.total_points,
        option.price_after_discount,
        option.card_name,
        option.vendor_name,
    )

