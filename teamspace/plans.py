"""Plan definitions. Limits are enforced in the views, not in the templates.

None means unlimited. Prices are display-only: this starter has no payment
provider, see the README.
"""

PLANS = {
    "free": {"label": "Free", "price": 0, "max_members": 3, "max_tasks": 10},
    "pro": {"label": "Pro", "price": 19, "max_members": 10, "max_tasks": None},
}

PLAN_CHOICES = [(k, v["label"]) for k, v in PLANS.items()]


def limit(plan, key):
    return PLANS[plan][key]


def within(plan, key, count):
    """True if one more item still fits under the plan limit."""
    cap = PLANS[plan][key]
    return cap is None or count < cap
